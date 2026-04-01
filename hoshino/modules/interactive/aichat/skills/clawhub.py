"""
Author: SheBot
Date: 2026-03-31
Description: ClawHub 客户端 - 纯 CLI 方案

使用 clawhub CLI 命令：
- search: 搜索 skills
- install: 安装 skill
"""
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger

from hoshino.config import get_plugin_config_by_name


@dataclass
class ClawHubSkill:
    """ClawHub skill 信息"""
    slug: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    score: float = 0.0
    source_url: str = ""
    
    def __post_init__(self):
        if not self.source_url:
            self.source_url = f"https://clawhub.ai/skills/{self.slug}"


class ClawHubClient:
    """ClawHub CLI 客户端"""
    
    def __init__(self):
        self._cache: Dict[str, ClawHubSkill] = {}
    
    def _run(self, *args, timeout: int = 30) -> Tuple[bool, str]:
        """运行 CLI 命令"""
        try:
            cmd = ["clawhub"] + list(args)
            
            # 从配置读取 token 并设置环境变量
            env = os.environ.copy()
            try:
                conf = get_plugin_config_by_name("aichat")
                if conf and conf.clawhub_token:
                    env["CLAWHUB_TOKEN"] = conf.clawhub_token
                    masked = conf.clawhub_token[:4] + "****" if len(conf.clawhub_token) > 4 else "****"
                    logger.info(f"ClawHub token 已加载: {masked}")
            except Exception:
                pass
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env
            )
            return result.returncode == 0, result.stdout or result.stderr
        except subprocess.TimeoutExpired:
            return False, "命令执行超时"
        except FileNotFoundError:
            return False, "clawhub CLI 未安装"
        except Exception as e:
            return False, str(e)
    
    async def search_skills(self, query: str, limit: int = 10) -> List[ClawHubSkill]:
        """搜索 skill
        
        CLI: clawhub search <query> --limit <limit>
        """
        logger.info(f"CLI 搜索: {query}")
        
        success, output = self._run("search", query, "--limit", str(limit))
        
        if not success:
            logger.error(f"CLI 搜索失败: {output}")
            return []
        
        return self._parse_search_output(output, limit)
    
    def _parse_search_output(self, output: str, limit: int) -> List[ClawHubSkill]:
        """解析搜索输出
        
        格式:
        china-stock-analysis  China Stock Analysis  (3.632)
        stock-monitor  Stock Monitor  (3.588)
        """
        skills = []
        lines = output.strip().split('\n')
        
        for line in lines[:limit]:
            line = line.strip()
            if not line:
                continue
            
            # 匹配: slug  name  (score)
            match = re.match(r'([\w\-]+)\s+(.+?)\s+\(([\d\.]+)\)\s*$', line)
            if match:
                slug = match.group(1)
                name = match.group(2).strip()
                score = float(match.group(3))
                
                skills.append(ClawHubSkill(
                    slug=slug,
                    name=name,
                    score=score,
                ))
            else:
                # 简单解析：第一部分是 slug，最后括号是 score
                parts = line.rsplit('(', 1)
                if len(parts) == 2 and parts[1].endswith(')'):
                    # 有分数
                    try:
                        score = float(parts[1][:-1])
                        front = parts[0].strip()
                        # 从前面分离 slug 和 name
                        front_parts = front.split(None, 1)
                        if len(front_parts) >= 2:
                            slug = front_parts[0]
                            name = front_parts[1]
                        else:
                            slug = front
                            name = front
                        
                        skills.append(ClawHubSkill(
                            slug=slug,
                            name=name,
                            score=score,
                        ))
                    except ValueError:
                        pass
        
        return skills
    
    async def download_skill(self, slug: str, target_dir: Path) -> Tuple[bool, str]:
        """下载/安装 skill
        
        CLI: clawhub install <slug> --dir <parent> --force
        
        注意: clawhub 会在 --dir 下创建 skills/<slug> 目录
        """
        import shutil
        import os
        
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # clawhub 会在 --dir 下创建 skills/ 子目录
        # 所以我们把 --dir 设为 target_dir 的父目录
        parent_dir = target_dir.parent
        
        logger.info(f"CLI 安装: {slug} 到 {parent_dir}")
        
        # 切换到目标目录执行，避免在当前目录创建 skills
        old_cwd = os.getcwd()
        try:
            os.chdir(parent_dir)
            success, output = self._run(
                "install", slug,
                "--force",
                timeout=60
            )
        finally:
            os.chdir(old_cwd)
        
        if not success:
            return False, f"安装失败: {output}"
        
        # clawhub 默认在当前目录创建 skills/<slug>
        installed_dir = parent_dir / "skills" / slug
        
        if not installed_dir.exists():
            # 尝试查找刚安装的目录
            skills_dir = parent_dir / "skills"
            if skills_dir.exists():
                for subdir in skills_dir.iterdir():
                    if subdir.is_dir() and subdir.name == slug:
                        installed_dir = subdir
                        break
        
        if not installed_dir.exists():
            return False, "安装后未找到 skill 目录"
        
        # 如果目标已存在，先删除
        if target_dir.exists():
            shutil.rmtree(target_dir)
        
        # 移动到目标位置
        shutil.move(str(installed_dir), str(target_dir))
        
        # 清理空的 skills 目录
        skills_dir = parent_dir / "skills"
        if skills_dir.exists() and not any(skills_dir.iterdir()):
            skills_dir.rmdir()
        
        # 创建 meta
        self._create_meta(target_dir, slug)
        
        return True, "1.0.0"
    
    def _create_meta(self, target_dir: Path, slug: str):
        """创建 _meta.json"""
        meta = {
            "source": "clawhub",
            "source_url": f"https://clawhub.ai/skills/{slug}",
            "slug": slug,
            "version": "1.0.0",
            "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "enabled": True,
        }
        (target_dir / "_meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
    
    async def update_skill(self, slug: str, target_dir: Path) -> Tuple[bool, str]:
        """更新 skill
        
        先备份旧版本，然后重新安装
        """
        import shutil
        import os
        
        target_dir = Path(target_dir)
        parent_dir = target_dir.parent
        
        logger.info(f"更新 skill: {slug}")
        
        # 备份旧版本
        backup_dir = None
        if target_dir.exists():
            backup_dir = parent_dir / f"{slug}.backup"
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            shutil.copytree(target_dir, backup_dir)
            logger.info(f"已备份到: {backup_dir}")
        
        # 先删除旧版本（避免 clawhub 跳过安装）
        if target_dir.exists():
            shutil.rmtree(target_dir)
        
        # 重新安装
        install_success, install_msg = await self.download_skill(slug, target_dir)
        
        if install_success:
            # 安装成功，删除备份
            if backup_dir and backup_dir.exists():
                shutil.rmtree(backup_dir)
            return True, "更新成功"
        else:
            # 安装失败，恢复备份
            if backup_dir and backup_dir.exists():
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                shutil.move(backup_dir, target_dir)
            return False, f"更新失败: {install_msg}"
    
    def parse_clawhub_reference(self, ref: str) -> str:
        """解析引用"""
        if ref.startswith("clawhub:"):
            ref = ref[8:]
        return ref.strip()


# 全局实例
clawhub_client = ClawHubClient()
