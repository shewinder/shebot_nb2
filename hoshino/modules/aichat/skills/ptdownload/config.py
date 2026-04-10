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
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class QBittorrentConfig(BaseModel):
    """qBittorrent 配置"""
    enabled: bool = False
    base_url: str = "http://localhost:8080"
    username: str = "admin"
    password: str = ""
    default_save_path: str = "/downloads"
    verify_ssl: bool = False


class PTStation(BaseModel):
    """PT 站配置"""
    name: str
    enabled: bool = True
    search_url: str
    search_method: str = "get"
    headers: Dict[str, str] = Field(default_factory=dict)
    result_selector: str = "table.torrents tr"
    field_mapping: Dict[str, str] = Field(default_factory=dict)


class Config(BaseModel):
    """PT Download Skill 配置"""
    qbittorrent: QBittorrentConfig = Field(default_factory=QBittorrentConfig)
    pt_stations: List[PTStation] = Field(default_factory=list)
    save_paths: Dict[str, str] = Field(default_factory=dict)

    def get_save_path(self, category: str) -> str:
        """根据分类获取保存路径"""
        defaults = {
            'movie': '/downloads/movies',
            'tv': '/downloads/tv',
            'anime': '/downloads/anime',
            'documentary': '/downloads/documentary',
            'music': '/downloads/music',
            'other': '/downloads/other'
        }
        return self.save_paths.get(
            category, 
            defaults.get(category, self.qbittorrent.default_save_path)
        )


def get_project_root() -> Path:
    """获取项目根目录（优先从环境变量读取）"""
    if project_root := os.environ.get("PROJECT_ROOT"):
        return Path(project_root)
    return Path("").resolve()


def get_user_config_path() -> Path:
    """获取用户配置文件路径"""
    config_path = get_project_root() / "data" / "config" / "ptdownload.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    return config_path


def load_config() -> Config:
    """加载配置"""
    user_config_path = get_user_config_path()
    
    if user_config_path.exists():
        try:
            data = json.loads(user_config_path.read_text(encoding='utf-8'))
            return Config.model_validate(data)
        except Exception as e:
            print(f"[警告] 加载配置失败: {e}，使用默认配置", file=os.sys.stderr)
    
    return Config()


# 全局配置实例
_config: Optional[Config] = None


def get_config() -> Config:
    """获取配置单例"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_qb_config() -> QBittorrentConfig:
    """获取 qBittorrent 配置"""
    return get_config().qbittorrent


def get_stations() -> List[PTStation]:
    """获取启用的 PT 站列表"""
    return [s for s in get_config().pt_stations if s.enabled]


def get_save_path(category: str) -> str:
    """根据分类获取保存路径"""
    return get_config().get_save_path(category)


def get_skill_dir() -> Path:
    """获取当前 Skill 目录"""
    if skill_dir := os.environ.get("SKILL_DIR"):
        return Path(skill_dir)
    return Path(__file__).parent
