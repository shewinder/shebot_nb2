"""工具访问层：编排层使用的工具获取接口

与 tools/__init__ 分离的原因：__init__ 负责导入全部内置工具完成注册，
其中 delegate_task 依赖 agent_loop → chat_executor；若 chat_executor
直接 import tools 会形成循环导入。本模块只依赖 registry 与 mcp，
编排层可安全在模块顶层导入。
"""
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from ..config import Config
from ..mcp import mcp_session_manager, mcp_tool_bridge
from .registry import get_available_tools as _get_registry_tools
from .registry import get_tool_function as _get_registry_tool_function


async def get_available_tools(session: Optional[Any] = None) -> List[Dict[str, Any]]:
    """获取所有可用工具（包括内置工具和 MCP 工具）

    支持渐进式加载：如果提供了 session，只返回会话中已激活的 MCP 工具；
    否则返回所有 MCP 工具（兼容旧模式）。

    Args:
        session: 可选的 Session 实例，用于渐进式加载 MCP 工具

    Returns:
        OpenAI tools 格式的列表
    """
    # 获取内置工具
    tools = _get_registry_tools()

    # 获取 MCP 工具（如果启用）
    try:
        conf = Config.get_instance('aichat')
        if conf.enable_mcp:
            if mcp_session_manager is None:
                logger.debug("[MCP] session_manager 未初始化，跳过 MCP 工具加载")
                return tools

            if session:
                # 确保 default_active 的 server 在新会话中自动激活
                await mcp_session_manager.ensure_default_servers_activated(session.session_id)

                # 渐进式加载：只获取会话中已激活的 MCP 工具
                active_servers = mcp_session_manager.get_active_servers(session.session_id)
                if active_servers:
                    mcp_tools_list = await mcp_tool_bridge.get_active_tool_schemas(session.session_id)
                    tools.extend(mcp_tools_list)
                    logger.info(f"[MCP] 会话 {session.session_id[:20]}... 加载 {len(mcp_tools_list)} 个 MCP 工具")
                else:
                    logger.debug(f"[MCP] 会话 {session.session_id[:20]}... 没有激活的 MCP server")
            else:
                # 无会话时，返回所有 MCP 工具（兼容旧模式）
                # 注意：这会连接所有 server，可能较慢
                mcp_tools_list = await mcp_tool_bridge.get_tool_schemas()
                tools.extend(mcp_tools_list)
                logger.info(f"[MCP] 加载所有 {len(mcp_tools_list)} 个 MCP 工具（无会话模式）")
    except Exception as e:
        logger.exception(f"[MCP] 获取 MCP 工具失败: {e}")

    # 过滤 wait_and_resume：仅后台 session 可见
    is_bg = session is not None and session.session_id.startswith("bg_task_")
    tools = [
        t for t in tools
        if t["function"]["name"] != "wait_and_resume" or is_bg
    ]

    # 过滤 blocked_tools：sub agent 禁止使用的工具
    if session is not None:
        blocked = getattr(session, '_blocked_tools', None)
        if blocked:
            tools = [
                t for t in tools
                if t["function"]["name"] not in blocked
            ]

    return tools


def get_tool_function(name: str) -> Optional[Callable]:
    """根据名称获取工具函数

    优先从内置工具查找，如果找不到且名称以 mcp_ 开头，则从 MCP 工具查找。

    Args:
        name: 工具名称

    Returns:
        工具函数，不存在返回 None
    """
    # 先尝试内置工具
    func = _get_registry_tool_function(name)
    if func:
        return func

    # 尝试 MCP 工具
    if name.startswith("mcp_"):
        try:
            return mcp_tool_bridge.get_tool_function(name)
        except Exception as e:
            logger.debug(f"获取 MCP 工具函数失败: {e}")

    return None
