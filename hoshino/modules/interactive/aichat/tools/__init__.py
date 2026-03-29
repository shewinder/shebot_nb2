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

# MCP 相关导入
from ..mcp import mcp_tool_bridge, mcp_server_manager
from ..config import Config


def get_available_tools() -> List[Dict[str, Any]]:
    """获取所有可用工具（包括内置工具和 MCP 工具）
    
    Returns:
        OpenAI tools 格式的列表
    """
    # 获取内置工具
    tools = _get_registry_tools()
    
    # 获取 MCP 工具（如果启用）
    try:
        conf = Config.get_instance('aichat')
        if conf.enable_mcp:
            mcp_tools = mcp_tool_bridge.get_tool_schemas()
            tools.extend(mcp_tools)
    except Exception as e:
        logger.debug(f"获取 MCP 工具失败: {e}")
    
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


__all__ = [
    # 核心类
    "Tool",
    "ToolRegistry",
    "tool_registry",
    # 兼容接口（已支持 MCP）
    "get_available_tools",
    "get_tool_function",
    # 工具返回辅助函数
    "ToolResult",
    "ok",
    "fail",
    # 内置工具模块（可选导出）
    "builtin",
]
