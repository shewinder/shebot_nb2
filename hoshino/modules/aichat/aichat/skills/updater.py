"""Skill 自更新能力层

为 skill_admin 工具提供：写前校验、写前备份、审计、回滚、热重载。
设计文档：docs/skill-self-update-design.md

关键约束（用户决策 A1/B1）：
- 内置 skill 只读：update 内置 skill 时复制到用户路径生成覆盖副本；
  delete 仅限用户路径；rollback 无备份时删除用户副本回退到内置。
- 管理操作默认 SUPERUSER（由 tools/permission.py 双层接线强制执行）。

文件 IO 同步执行（项目决策：暂不异步化）；写操作用全局锁串行化。
"""
import json
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from ..config import Config
from .discovery import parse_frontmatter
from .manager import skill_manager

conf = Config.get_instance('aichat')

SKILL_NAME_RE = re.compile(r"^[a-z0-9_-]{1,50}$")
MAX_SKILL_MD_SIZE = 50 * 1024       # SKILL.md 大小上限
MAX_SCRIPT_SIZE = 100 * 1024        # 单个脚本大小上限
MAX_SCRIPTS = 10                    # 单 skill 脚本文件数上限
BACKUP_KEEP = 5                     # 每 skill 备份保留份数
BACKUP_DIR_NAME = ".backup"
CHANGES_LOG_NAME = ".changes.jsonl"

# 写操作全局锁：创建/更新/回滚/删除互斥，防并发写坏同一 skill
_write_lock = threading.Lock()


def _user_skill_dir() -> Path:
    """用户 skill 根目录（skill_user_paths[0]，不存在则创建）"""
    path = Path(conf.skill_user_paths[0]) if conf.skill_user_paths else Path("data/skills")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _backup_dir() -> Path:
    return _user_skill_dir() / BACKUP_DIR_NAME


def _changes_log() -> Path:
    return _user_skill_dir() / CHANGES_LOG_NAME


# ========== 校验 ==========


def validate_skill_name(name: Optional[str]) -> Tuple[bool, str]:
    """名称只允许小写字母/数字/下划线/连字符，长度 1-50，杜绝路径遍历"""
    if not name or not SKILL_NAME_RE.match(name):
        return False, "名称只允许小写字母/数字/下划线/连字符，长度 1-50"
    return True, ""


def _render_skill_md(name: str, description: str, content: str) -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{content.strip()}\n"


def _validate_rendered(skill_md: str) -> Tuple[bool, str]:
    if len(skill_md.encode("utf-8")) > MAX_SKILL_MD_SIZE:
        return False, f"SKILL.md 超过 {MAX_SKILL_MD_SIZE // 1024}KB 上限"
    metadata, _ = parse_frontmatter(skill_md)
    if metadata is None:
        return False, "SKILL.md frontmatter 非法"
    if not metadata.get("name") or not metadata.get("description"):
        return False, "frontmatter 缺少 name/description"
    return True, ""


def _validate_scripts(target_dir: Path, scripts: Dict[str, str]) -> Tuple[bool, str]:
    """校验脚本字典：相对路径、无遍历、数量与大小限制"""
    existing = 0
    scripts_dir = target_dir / "scripts"
    if scripts_dir.is_dir():
        existing = sum(1 for p in scripts_dir.rglob("*") if p.is_file())

    if existing + len(scripts) > MAX_SCRIPTS:
        return False, f"脚本文件数超过 {MAX_SCRIPTS} 个上限"

    for rel_path, content in scripts.items():
        if rel_path.startswith("/") or ".." in rel_path:
            return False, f"脚本路径非法: {rel_path}"
        if len(content.encode("utf-8")) > MAX_SCRIPT_SIZE:
            return False, f"脚本 {rel_path} 超过 {MAX_SCRIPT_SIZE // 1024}KB 上限"
    return True, ""


# ========== 备份 / 审计 / 热重载 ==========


def _backup(target_dir: Path, name: str) -> str:
    """整目录复制到 .backup/<name>/<ts>/，轮换保留最近 BACKUP_KEEP 份，返回备份 id"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = _backup_dir() / name / ts
    shutil.copytree(target_dir, dest)

    backups = sorted((_backup_dir() / name).iterdir(), reverse=True)
    for old in backups[BACKUP_KEEP:]:
        shutil.rmtree(old, ignore_errors=True)
        logger.debug(f"[SkillUpdater] 轮换删除旧备份: {old.name}")
    return ts


def _restore_backup(name: str, backup_id: str) -> None:
    """用指定备份恢复 skill 目录（先清空再复制）"""
    target = _user_skill_dir() / name
    src = _backup_dir() / name / backup_id
    if not src.is_dir():
        return
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(src, target)


def _list_backups(name: str) -> List[str]:
    """按时间倒序返回备份 id 列表"""
    dir_path = _backup_dir() / name
    if not dir_path.is_dir():
        return []
    return sorted((p.name for p in dir_path.iterdir() if p.is_dir()), reverse=True)


def _audit(action: str, name: str, user_id: Optional[int], group_id: Optional[int], detail: Dict[str, Any]) -> None:
    record = {
        "ts": time.time(),
        "action": action,
        "skill": name,
        "user_id": user_id,
        "group_id": group_id,
        **detail,
    }
    try:
        with open(_changes_log(), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"[SkillUpdater] 审计写入失败: {e}")


def reload_skills() -> List[str]:
    """热重载：user_paths 与 conf 对齐后重扫，返回当前全部 skill 名称"""
    skill_manager.user_paths = list(conf.skill_user_paths)
    skill_manager.reload()
    return [s.metadata.name for s in skill_manager.list_skills()]


def _reload_and_verify(name: str) -> bool:
    """reload 后确认目标 skill 存在（解析失败 → False，触发自动回滚）"""
    reload_skills()
    return skill_manager.get_skill(name) is not None


def _write_target(target_dir: Path, skill_md: str, scripts: Optional[Dict[str, str]]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    for rel_path, content in (scripts or {}).items():
        script_path = (target_dir / rel_path).resolve()
        # 双保险：解析后的路径必须仍在 skill 目录内
        if not str(script_path).startswith(str(target_dir.resolve())):
            raise ValueError(f"脚本路径越界: {rel_path}")
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(content, encoding="utf-8")


# ========== 对外操作（均持锁） ==========


def create_skill(
    name: str,
    description: str,
    content: str,
    scripts: Optional[Dict[str, str]] = None,
    *,
    user_id: Optional[int] = None,
    group_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """创建新用户 skill 并热加载"""
    ok, msg = validate_skill_name(name)
    if not ok:
        return False, msg

    with _write_lock:
        target = _user_skill_dir() / name
        if target.exists():
            return False, f"用户 skill '{name}' 已存在，请使用 update_skill"

        user_skills = [d for d in _user_skill_dir().iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
        if len(user_skills) >= conf.skill_max_user_skills:
            return False, f"用户 skill 数量已达上限（{conf.skill_max_user_skills}），请先删除不再需要的"

        skill_md = _render_skill_md(name, description, content)
        ok, msg = _validate_rendered(skill_md)
        if not ok:
            return False, msg
        ok, msg = _validate_scripts(target, scripts or {})
        if not ok:
            return False, msg

        try:
            _write_target(target, skill_md, scripts)
        except Exception as e:
            logger.exception(f"[SkillUpdater] 创建 skill 写入失败: {e}")
            shutil.rmtree(target, ignore_errors=True)
            return False, f"写入失败: {e}"

        _audit("create", name, user_id, group_id, {"size": len(skill_md)})
        if not _reload_and_verify(name):
            shutil.rmtree(target, ignore_errors=True)
            return False, "创建后校验失败，已撤销写入"

        logger.info(f"[SkillUpdater] 创建 skill: {name} (user={user_id})")
        return True, f"✅ 已创建 skill '{name}' 并热加载，下一轮对话即可激活使用"


def update_skill(
    name: str,
    content: Optional[str] = None,
    description: Optional[str] = None,
    scripts: Optional[Dict[str, str]] = None,
    *,
    user_id: Optional[int] = None,
    group_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """更新 skill（写前备份）；内置 skill 自动转为用户副本（B1）"""
    ok, msg = validate_skill_name(name)
    if not ok:
        return False, msg

    with _write_lock:
        target = _user_skill_dir() / name
        skill = skill_manager.get_skill(name)

        if not target.exists():
            if skill is None:
                return False, f"SKILL '{name}' 不存在"
            # 内置 skill：复制到用户路径再改（内置文件保持只读）
            try:
                shutil.copytree(skill.directory, target, dirs_exist_ok=True)
            except Exception as e:
                logger.exception(f"[SkillUpdater] 复制内置 skill 失败: {e}")
                return False, f"复制内置 skill 失败: {e}"

        try:
            raw = (target / "SKILL.md").read_text(encoding="utf-8")
        except Exception as e:
            return False, f"读取现有 SKILL.md 失败: {e}"
        metadata, body = parse_frontmatter(raw)
        if metadata is None:
            return False, "现有 SKILL.md 解析失败，拒绝修改"

        new_description = (description or "").strip() or metadata.get("description", "")
        new_content = content if content is not None else body
        skill_md = _render_skill_md(name, new_description, new_content)
        ok, msg = _validate_rendered(skill_md)
        if not ok:
            return False, msg
        ok, msg = _validate_scripts(target, scripts or {})
        if not ok:
            return False, msg

        try:
            backup_id = _backup(target, name)
            _write_target(target, skill_md, scripts)
        except Exception as e:
            logger.exception(f"[SkillUpdater] 更新 skill 写入失败: {e}")
            return False, f"写入失败: {e}"

        _audit("update", name, user_id, group_id, {
            "size": len(skill_md),
            "backup_id": backup_id,
            "from_builtin": skill is not None and skill.directory != target,
        })
        if not _reload_and_verify(name):
            _restore_backup(name, backup_id)
            reload_skills()
            return False, "更新后校验失败，已自动回滚到上一版本"

        logger.info(f"[SkillUpdater] 更新 skill: {name} (user={user_id})")
        return True, f"✅ 已更新 skill '{name}' 并热加载（备份: {backup_id}）"


def delete_skill(
    name: str,
    *,
    user_id: Optional[int] = None,
    group_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """删除用户 skill；内置 skill 只读拒绝"""
    ok, msg = validate_skill_name(name)
    if not ok:
        return False, msg

    with _write_lock:
        target = _user_skill_dir() / name
        if not target.exists():
            if skill_manager.get_skill(name) is not None:
                return False, f"'{name}' 是内置 skill（只读），无法删除"
            return False, f"SKILL '{name}' 不存在"

        try:
            backup_id = _backup(target, name)
            shutil.rmtree(target)
        except Exception as e:
            logger.exception(f"[SkillUpdater] 删除 skill 失败: {e}")
            return False, f"删除失败: {e}"

        _audit("delete", name, user_id, group_id, {"backup_id": backup_id})
        reload_skills()
        logger.info(f"[SkillUpdater] 删除 skill: {name} (user={user_id})")
        return True, f"✅ 已删除用户 skill '{name}'（备份保留于 {backup_id}）"


def rollback_skill(
    name: str,
    *,
    user_id: Optional[int] = None,
    group_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """回滚到最近一次备份；无备份时删除用户副本（回退到内置版本）"""
    ok, msg = validate_skill_name(name)
    if not ok:
        return False, msg

    with _write_lock:
        target = _user_skill_dir() / name
        backups = _list_backups(name)

        if not backups:
            if target.exists():
                try:
                    shutil.rmtree(target)
                    reload_skills()
                except Exception as e:
                    return False, f"回滚失败: {e}"
                _audit("rollback", name, user_id, group_id, {"to": "builtin_or_none"})
                if skill_manager.get_skill(name) is not None:
                    return True, f"✅ 已删除用户副本，'{name}' 回退到内置版本"
                return True, f"✅ 已删除用户 skill '{name}'"
            return False, f"'{name}' 没有可回滚的备份"

        backup_id = backups[0]
        try:
            _restore_backup(name, backup_id)
        except Exception as e:
            logger.exception(f"[SkillUpdater] 回滚失败: {e}")
            return False, f"回滚失败: {e}"

        _audit("rollback", name, user_id, group_id, {"backup_id": backup_id})
        if not _reload_and_verify(name):
            return False, "回滚后校验失败，请检查备份目录"
        logger.info(f"[SkillUpdater] 回滚 skill: {name} → {backup_id} (user={user_id})")
        return True, f"✅ 已回滚 '{name}' 到备份 {backup_id} 并热加载"
