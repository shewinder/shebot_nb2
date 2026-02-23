from typing import List, Optional
from pydantic import BaseModel

from hoshino.config import BaseConfig, configuration


class ApiEntry(BaseModel):
    """单个大模型 API 配置"""
    id: str = ""
    name: str = ""
    api_base: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-chat"
    max_tokens: Optional[int] = None  # 不填则用全局默认
    temperature: Optional[float] = None  # 不填则用全局默认
    supports_multimodal: Optional[bool] = None  # 是否支持多模态（图片），None 表示未配置，默认 False


@configuration('aichat')
class Config(BaseConfig):
    """AI Chat插件配置"""
    # 多 API 配置（优先使用；为空时使用下方单 API 配置）
    apis: List[ApiEntry] = []
    default_api: str = ""  # 默认使用的 API id，为空则取 apis[0] 或单 API

    # 单 API 配置（兼容旧版；当 apis 为空时生效）
    api_base: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-chat"

    # Session 配置
    max_history: int = 100
    session_timeout: int = 3600  # 秒，0 表示永不过期

    # 全局默认（单 API 及 apis 中未指定时使用）
    max_tokens: int = 8192
    temperature: float = 0.7

    # 人格配置
    default_persona: str = ""
    max_saved_personas: int = 5

    def get_api_list(self) -> List[ApiEntry]:
        """获取有效的 API 列表（多 API 或从单 API 构造一个）"""
        if self.apis:
            return self.apis
        # 兼容：从单 API 构造
        return [
            ApiEntry(
                id="default",
                name="默认",
                api_base=self.api_base,
                api_key=self.api_key,
                model=self.model,
            )
        ]

    def get_default_api_id(self) -> str:
        """获取默认 API 的 id"""
        lst = self.get_api_list()
        if not lst:
            return ""
        if self.default_api and any(a.id == self.default_api for a in lst):
            return self.default_api
        return lst[0].id

    def get_api_by_id(self, api_id: str) -> Optional[ApiEntry]:
        """根据 id 获取 API 配置"""
        for a in self.get_api_list():
            if a.id == api_id:
                return a
        return None
