"""
PT 下载 Skill 配置管理
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator


DEFAULT_SAVE_PATHS: dict[str, str] = {}

DEFAULT_PT_STATIONS = [
    {
        "name": "北洋园",
        "enabled": True,
        "search_url": "https://tjupt.org/torrents.php?search={keyword}",
        "search_method": "get",
        "headers": {"Cookie": "在此填写你的北洋园 Cookie"},
        "result_selector": "table.torrents tr.sticky_bg, table.torrents tr.normal_bg",
        "field_mapping": {
            "title": "table.torrentname a[href*='details.php?id=']",
            "download": "a[href*='download.php?id=']",
            "size": "td.rowfollow:nth-of-type(5)",
            "seeders": "td.rowfollow:nth-of-type(6)"
        }
    },
    {
        "name": "audiences",
        "enabled": True,
        "search_url": "https://audiences.me/torrents.php?search={keyword}",
        "search_method": "get",
        "headers": {"Cookie": "在此填写你的 audiences Cookie"},
        "result_selector": "table.torrents tr",
        "field_mapping": {
            "title": "a[href*='details.php']",
            "download": "a[href*='download.php']",
            "size": "td:nth-child(5)",
            "seeders": "td:nth-child(6)"
        }
    }
]


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

    @field_validator("save_paths")
    @classmethod
    def set_default_save_paths(cls, v: Dict[str, str]) -> Dict[str, str]:
        if not DEFAULT_SAVE_PATHS:
            return v
        result = DEFAULT_SAVE_PATHS.copy()
        result.update(v)
        return result

    def get_save_path(self, category: str) -> str:
        """根据分类获取保存路径"""
        return self.save_paths.get(category, self.qbittorrent.default_save_path)


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


def create_default_config() -> Config:
    """创建带默认站点的配置"""
    return Config(
        qbittorrent=QBittorrentConfig(),
        pt_stations=[PTStation(**s) for s in DEFAULT_PT_STATIONS],
        save_paths=DEFAULT_SAVE_PATHS.copy()
    )


def save_config_to_file(config: Config, path: Path) -> None:
    """保存配置到 JSON 文件"""
    data = {
        "_comment": "PT 下载 Skill 配置文件，请填写 Cookie 后使用",
        "_warning": "此文件包含敏感信息(Cookie/密码)，不要提交到 git",
        **config.model_dump()
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def load_config() -> Config:
    """加载配置（首次运行自动生成）"""
    config_path = get_user_config_path()
    
    if not config_path.exists():
        # 首次运行：生成默认配置
        config = create_default_config()
        save_config_to_file(config, config_path)
        print(f"[提示] 已生成默认配置: {config_path}", file=os.sys.stderr)
        print(f"[提示] 请编辑配置文件，填写 PT 站 Cookie 后重新运行", file=os.sys.stderr)
        return config
    
    # 加载用户配置
    try:
        data = json.loads(config_path.read_text(encoding='utf-8'))
        return Config.model_validate(data)
    except Exception as e:
        print(f"[警告] 加载配置失败: {e}，使用默认配置", file=os.sys.stderr)
        return create_default_config()


# 全局配置单例
_config: Config | None = None


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
