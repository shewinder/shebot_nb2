# 从 registry 导出核心类和方法
from .registry import (
    Tool,
    ToolRegistry,
    tool_registry,
    get_available_tools,
    get_tool_function,
    # 工具返回辅助函数
    ToolResult,
    ok,
    fail,
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
    # 工具返回辅助函数
    "ToolResult",
    "ok",
    "fail",
    # 内置工具模块（可选导出）
    "builtin",
]
