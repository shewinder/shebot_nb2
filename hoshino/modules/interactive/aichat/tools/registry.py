"""
AI Tool/Function Calling 工具注册器
提供注册式工具管理，支持装饰器注册和 Session 自动注入
"""
import functools
import inspect
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from pydantic import BaseModel

from .context import tool_call_context

if TYPE_CHECKING:
    from ..session import Session


class Tool(BaseModel):
    """工具定义数据类"""
    name: str
    description: str
    parameters: Dict[str, Any]
    function: Callable
    inject_session: bool = False  # 是否自动注入 session

    class Config:
        arbitrary_types_allowed = True


class ToolRegistry:
    """
    工具注册器 - 管理所有 AI 可调用工具
    
    使用装饰器方式注册工具：
        @tool_registry.register(
            name="tool_name",
            description="工具描述",
            parameters={...}
        )
        async def my_tool(...):
            ...
    """
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
    
    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        inject_session: bool = False
    ) -> Callable[[Callable], Callable]:
        """
        装饰器：注册一个工具
        
        Args:
            name: 工具名称（唯一标识）
            description: 工具描述，帮助 AI 理解工具用途
            parameters: JSON Schema 格式的参数定义
            inject_session: 是否自动注入 session 参数（默认 False）
            
        Returns:
            装饰器函数
            
        Example:
            @tool_registry.register(
                name="web_search",
                description="搜索网页获取信息",
                parameters={...}
            )
            async def web_search(query: str) -> Dict[str, Any]:
                ...
            
            @tool_registry.register(
                name="edit_image",
                description="编辑图片",
                parameters={...},
                inject_session=True  # 自动注入 session
            )
            async def edit_image(prompt: str, session: Optional["Session"] = None):
                ...
        """
        def decorator(func: Callable) -> Callable:
            # 如果启用 session 注入，包装函数
            if inject_session:
                func = self._wrap_with_session_injection(func)
            
            self._tools[name] = Tool(
                name=name,
                description=description,
                parameters=parameters,
                function=func,
                inject_session=inject_session
            )
            return func
        return decorator
    
    def _wrap_with_session_injection(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """
        包装函数，自动注入 session 参数
        
        如果函数签名包含 `session` 参数且调用时未提供，
        自动从 tool_call_context 获取并注入
        """
        sig = inspect.signature(func)
        has_session_param = 'session' in sig.parameters
        
        if not has_session_param:
            # 函数没有 session 参数，无需包装
            return func
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if 'session' not in kwargs:
                # 从 contextvars 获取 session
                ctx = tool_call_context.get()
                if ctx and 'session' in ctx:
                    kwargs['session'] = ctx['session']
            return await func(*args, **kwargs)
        
        return wrapper
    
    def get_schemas(self) -> List[Dict[str, Any]]:
        """
        获取所有已注册工具的 OpenAI 格式 schema
        
        Returns:
            OpenAI tools 格式的列表
        """
        schemas = []
        for name, tool in self._tools.items():
            schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            }
            schemas.append(schema)
        return schemas
    
    def get_tool(self, name: str) -> Optional[Callable]:
        """
        根据名称获取工具函数
        
        Args:
            name: 工具名称
            
        Returns:
            工具函数，如果不存在则返回 None
        """
        tool = self._tools.get(name)
        return tool.function if tool else None
    
    def list_tools(self) -> List[str]:
        """
        列出所有已注册工具的名称
        
        Returns:
            工具名称列表
        """
        return list(self._tools.keys())
    
    def has_tool(self, name: str) -> bool:
        """
        检查工具是否已注册
        
        Args:
            name: 工具名称
            
        Returns:
            是否已注册
        """
        return name in self._tools
    
    def get_tool_info(self, name: str) -> Optional[Tool]:
        """
        获取工具的完整信息
        
        Args:
            name: 工具名称
            
        Returns:
            Tool 对象，如果不存在则返回 None
        """
        return self._tools.get(name)


# 全局注册器实例
tool_registry = ToolRegistry()

# 兼容旧接口
get_available_tools = tool_registry.get_schemas
get_tool_function = tool_registry.get_tool
