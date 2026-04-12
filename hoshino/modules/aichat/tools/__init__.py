from typing import Any, Callable, Dict, List, Optional

from loguru import logger

# 从 registry 导出核心类和方法
from .registry import (
    Tool,
    ToolRegistry,
    tool_registry,
    get_available_tools as _get_registry_tools,
    get_tool_function as _get_registry_tool_function,
    # 工具返回辅助函数
    ToolResult,
    ok,
    fail,
)

# 导入内置工具，使其自动注册
from .builtin import generate_image
from .builtin import environment
from .builtin import mcp_tools  # MCP 相关工具

from ..config import Config


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
            # 延迟导入 MCP 模块以避免初始化问题
            from ..mcp import mcp_session_manager, mcp_tool_bridge
            
            if mcp_session_manager is None:
                logger.debug("[MCP] session_manager 未初始化，跳过 MCP 工具加载")
                return tools
            
            if session:
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
            from ..mcp import mcp_tool_bridge
            return mcp_tool_bridge.get_tool_function(name)
        except Exception as e:
            logger.debug(f"获取 MCP 工具函数失败: {e}")
    
    return None


__all__ = [
    # 核心类
    "Tool",
    "ToolRegistry",
    "tool_registry",
    # 兼容接口（已支持 MCP 渐进式加载）
    "get_available_tools",
    "get_tool_function",
    # 工具返回辅助函数
    "ToolResult",
    "ok",
    "fail",
    # 内置工具模块（可选导出）
    "builtin",
]
