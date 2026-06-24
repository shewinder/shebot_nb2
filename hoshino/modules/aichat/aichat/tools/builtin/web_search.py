"""AI 工具：网页搜索 — 启动注册入口。

切换逻辑见 search_providers/__init__.py → switch_provider()。
"""
from hoshino.modules.aichat.aichat.config import Config as AIChatConfig

from ..registry import tool_registry
from .search_providers import get_provider, get_tool_fn

_config = AIChatConfig.get_instance("aichat")
_name = _config.search_provider
_provider = get_provider(_name)

tool_registry.register(
    name="web_search",
    description=_provider["description"],
    parameters=_provider["parameters"],
)(get_tool_fn(_name))
