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
    # 多 API 配置（默认提供一个示例模板）
    apis: List[ApiEntry] = [
        ApiEntry(
            id="deepseek",
            name="DeepSeek",
            api_base="https://api.deepseek.com",
            api_key="your-api-key-here",
            model="deepseek-chat",
        )
    ]
    default_api: str = "deepseek"  # 默认使用的 API id，为空则取 apis[0]

    # Session 配置
    max_history: int = 100
    session_timeout: int = 3600  # 秒，0 表示永不过期

    # 全局默认（单 API 及 apis 中未指定时使用）
    max_tokens: int = 8192
    temperature: float = 0.7

    # 人格配置
    default_persona: str = ""
    max_saved_personas: int = 5

    # Markdown 渲染配置
    enable_markdown_render: bool = True  # 是否启用 Markdown 自动渲染
    markdown_min_length: int = 100  # 触发渲染的最小文本长度
    markdown_preview_length: int = 50  # 预览文本长度（图片描述）

    def get_api_list(self) -> List[ApiEntry]:
        """获取 API 列表"""
        return self.apis

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
