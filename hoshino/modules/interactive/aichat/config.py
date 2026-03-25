from typing import List, Optional
from pydantic import BaseModel

from hoshino.config import BaseConfig, configuration


class ApiEntry(BaseModel):
    """单个厂商配置"""
    api: str = ""              # 厂商唯一标识（如 "kimi", "deepseek"）
    api_base: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-chat"
    supports_multimodal: Optional[bool] = None
    supports_tools: Optional[bool] = True
    max_tokens: Optional[int] = None  # None 表示不传给 API，使用模型默认值
    temperature: Optional[float] = None  # None 表示不传给 API，使用模型默认值


@configuration('aichat')
class Config(BaseConfig):
    """AI Chat插件配置"""
    # 厂商列表
    apis: List[ApiEntry] = [
        ApiEntry(
            api="deepseek",
            api_base="https://api.deepseek.com",
            api_key="your-api-key-here",
            model="deepseek-chat",
        )
    ]

    # 当前选择
    current_api: str = ""  # 当前厂商（空或无效则使用 apis[0]）

    # Session 配置
    max_history: int = 100
    session_timeout: int = 3600  # 秒，0 表示永不过期

    # 人格配置
    default_persona: str = ""

    # Markdown 渲染配置
    enable_markdown_render: bool = False
    markdown_min_length: int = 100

    # 图片生成模型配置
    image_generation_model: str = "doubao-seedream-5-0-260128"  # 用于图片生成的模型名称
    image_edit_model: str = "gpt-image-1"  # 用于图片编辑的模型名称（如 dall-e-2），空表示不支持编辑

    def get_apis(self) -> List[ApiEntry]:
        """获取厂商列表"""
        return self.apis

    def get_api_by_name(self, api: str) -> Optional[ApiEntry]:
        """根据 api 名称获取配置"""
        for a in self.apis:
            if a.api == api:
                return a
        return None

    def get_current_api(self) -> str:
        """获取当前厂商（无效时返回第一个）"""
        if self.current_api and self.get_api_by_name(self.current_api):
            return self.current_api
        return self.apis[0].api if self.apis else ""

    def set_current_api(self, api: str) -> bool:
        """设置当前厂商"""
        if not self.get_api_by_name(api):
            return False
        self.current_api = api
        return True
