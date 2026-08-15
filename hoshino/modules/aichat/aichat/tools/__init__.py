"""AI 工具包

__init__ 是纯再导出枢纽，不再负责内置工具注册——
注册动作由插件入口 aichat/__init__.py 显式执行
（`from .tools import builtin` + `from .tools.builtin import mcp_tools`）。

原因：若 __init__ 导入内置工具，其中 delegate_task/scheduler/background_task
依赖 agent_loop → chat_executor，而 chat_executor 又 import tools 包，
会形成循环导入。工具获取接口在 access.py，可安全被编排层导入。
"""
from .registry import (
    Tool,
    ToolRegistry,
    tool_registry,
    # 工具返回辅助函数
    ToolResult,
    ok,
    fail,
)

from .access import get_available_tools, get_tool_function

__all__ = [
    # 核心类
    "Tool",
    "ToolRegistry",
    "tool_registry",
    # 工具获取接口（已支持 MCP 渐进式加载）
    "get_available_tools",
    "get_tool_function",
    # 工具返回辅助函数
    "ToolResult",
    "ok",
    "fail",
]
