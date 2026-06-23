"""磁力下载 Skill 配置管理

从环境变量读取 qBittorrent 连接配置，与 ptdownload/qb_add.py 保持一致。
"""
import os
from typing import Optional


def get_qb_config() -> Optional[dict]:
    """读取 qBittorrent 连接配置（仅环境变量）"""
    base_url = os.environ.get("PT_QB_URL", "")
    if not base_url:
        return None
    return {
        "base_url": base_url,
        "username": os.environ.get("PT_QB_USERNAME", "admin"),
        "password": os.environ.get("PT_QB_PASSWORD", ""),
        "default_save_path": os.environ.get("PT_QB_SAVE_PATH", "/downloads"),
        "verify_ssl": False,
    }


def get_save_path(category: str) -> str:
    """根据分类拼接保存路径"""
    config = get_qb_config()
    if not config:
        return "/downloads"
    base = config["default_save_path"].rstrip("/")
    return f"{base}/{category}" if category else base
