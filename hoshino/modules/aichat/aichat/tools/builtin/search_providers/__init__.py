"""搜索 Provider 注册表 & 热切换"""
from loguru import logger

from . import youcom, iqs

_PROVIDERS = {
    "youcom": youcom.PROVIDER,
    "iqs": iqs.PROVIDER,
}

_MODULES = {
    "youcom": youcom,
    "iqs": iqs,
}


def get_provider(name: str) -> dict | None:
    return _PROVIDERS.get(name)


def get_tool_fn(name: str):
    """获取 provider 的 tool_fn，未找到返回 youcom 的作为 fallback"""
    mod = _MODULES.get(name, _MODULES["youcom"])
    return mod.tool_fn


def list_providers() -> list[str]:
    return list(_PROVIDERS.keys())


async def switch_provider(name: str) -> bool:
    """
    热切换搜索后端：持久化配置 + 重新注册 tool schema。
    被 admin command 或外部管理接口调用。
    """
    provider = get_provider(name)
    if not provider:
        logger.warning(f"未知的搜索 provider: {name}, 可用: {list_providers()}")
        return False

    from hoshino.config import save_plugin_config
    from hoshino.modules.aichat.aichat.config import Config as AIChatConfig
    from hoshino.modules.aichat.aichat.tools.registry import tool_registry

    # 1. 持久化
    config = AIChatConfig.get_instance("aichat")
    config.search_provider = name
    save_plugin_config("aichat", config)

    # 2. 重新注册 tool（覆盖同名）
    tool_registry.register(
        name="web_search",
        description=provider["description"],
        parameters=provider["parameters"],
    )(get_tool_fn(name))

    logger.info(f"搜索后端已切换: {provider['label']}")
    return True
