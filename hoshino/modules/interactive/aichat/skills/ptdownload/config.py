"""
PT 下载 Skill 配置管理

环境变量（由 execute_script 自动注入）：
- PROJECT_ROOT: 项目根目录（Path("").resolve()）
- SKILL_NAME: 当前 Skill 名称
- SKILL_DIR: 当前 Skill 目录
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional


# 默认配置（内置，不存储敏感信息）
DEFAULT_CONFIG: Dict[str, Any] = {
    "qbittorrent": {
        "enabled": False,
        "base_url": "http://localhost:8080",
        "username": "admin",
        "password": "",
        "default_save_path": "/downloads",
        "verify_ssl": False
    },
    "pt_stations": []
}


def get_project_root() -> Path:
    """获取项目根目录（优先从环境变量读取）"""
    if project_root := os.environ.get("PROJECT_ROOT"):
        return Path(project_root)
    # 回退：假设当前工作目录是项目根目录
    return Path("").resolve()


def get_user_config_path() -> Path:
    """获取用户配置文件路径"""
    config_path = get_project_root() / "data" / "config" / "ptdownload.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    return config_path


def load_config() -> Dict[str, Any]:
    """加载配置（用户配置优先于默认配置）"""
    user_config_path = get_user_config_path()
    
    if user_config_path.exists():
        try:
            user_config = json.loads(user_config_path.read_text(encoding='utf-8'))
            merged = DEFAULT_CONFIG.copy()
            merged.update(user_config)
            return merged
        except Exception as e:
            print(f"[警告] 加载配置失败: {e}，使用默认配置", file=os.sys.stderr)
    
    return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> bool:
    """保存配置到用户目录"""
    try:
        get_user_config_path().write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        return True
    except Exception as e:
        print(f"[错误] 保存配置失败: {e}", file=os.sys.stderr)
        return False


def get_qb_config() -> Optional[Dict[str, Any]]:
    """获取 qBittorrent 配置"""
    return load_config().get('qbittorrent')


def get_stations() -> List[Dict[str, Any]]:
    """获取启用的 PT 站列表"""
    stations = load_config().get('pt_stations', [])
    return [s for s in stations if s.get('enabled', True)]


def get_skill_dir() -> Path:
    """获取当前 Skill 目录（用于读取其他文件）"""
    if skill_dir := os.environ.get("SKILL_DIR"):
        return Path(skill_dir)
    return Path(__file__).parent
