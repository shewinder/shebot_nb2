"""
AI Tool/Function Calling 工具定义
提供注册式工具管理，支持装饰器注册

Usage:
    from .tools import tool_registry, get_available_tools, get_tool_function
    
    # 注册新工具
    @tool_registry.register(
        name="my_tool",
        description="工具描述",
        parameters={...}
    )
    async def my_tool(...) -> Dict[str, Any]:
        ...
    
    # 获取工具列表（OpenAI 格式）
    tools = get_available_tools()
    
    # 获取工具函数
    tool_func = get_tool_function("my_tool")
"""

# 从 registry 导出核心类和方法
from .registry import (
    Tool,
    ToolRegistry,
    tool_registry,
    get_available_tools,
    get_tool_function,
)

# 导入内置工具，使其自动注册
from .builtin import generate_image

__all__ = [
    # 核心类
    "Tool",
    "ToolRegistry",
    "tool_registry",
    # 兼容接口
    "get_available_tools",
    "get_tool_function",
    # 内置工具模块（可选导出）
    "builtin",
]
