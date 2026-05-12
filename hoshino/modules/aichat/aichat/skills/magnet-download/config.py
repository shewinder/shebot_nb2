"""磁力下载 Skill 配置管理

复用 ptdownload Skill 的 qBittorrent 连接配置。
配置文件路径: data/config/ptdownload.json
"""
import json
import os
from pathlib import Path
from typing import Optional


def get_project_root() -> Path:
    if project_root := os.environ.get("PROJECT_ROOT"):
        return Path(project_root)
    return Path("").resolve()


def get_config_path() -> Path:
    return get_project_root() / "data" / "config" / "ptdownload.json"


def get_qb_config() -> Optional[dict]:
    """读取 qBittorrent 连接配置"""
    config_path = get_config_path()
    if not config_path.exists():
        return None

    try:
        data = json.loads(config_path.read_text(encoding='utf-8'))
        qb = data.get("qbittorrent", {})
        if not qb.get("enabled"):
            return None
        return {
            "base_url": qb.get("base_url", "http://localhost:8080"),
            "username": qb.get("username", "admin"),
            "password": qb.get("password", ""),
            "default_save_path": qb.get("default_save_path", "/downloads"),
            "verify_ssl": qb.get("verify_ssl", False),
            "save_paths": data.get("save_paths", {}),
        }
    except Exception:
        return None


def get_save_path(category: str) -> str:
    """根据分类获取保存路径，优先 category 映射，否则默认路径"""
    config = get_qb_config()
    if not config:
        return "/downloads"
    save_paths = config.get("save_paths", {})
    return save_paths.get(category, config.get("default_save_path", "/downloads"))
