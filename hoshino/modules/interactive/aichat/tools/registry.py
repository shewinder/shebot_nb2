"""
AI Tool/Function Calling 工具注册器
提供注册式工具管理，支持装饰器注册
"""
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel


class Tool(BaseModel):
    """工具定义数据类"""
    name: str
    description: str
    parameters: Dict[str, Any]
    function: Callable

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
        parameters: Dict[str, Any]
    ) -> Callable[[Callable], Callable]:
        """
        装饰器：注册一个工具
        
        Args:
            name: 工具名称（唯一标识）
            description: 工具描述，帮助 AI 理解工具用途
            parameters: JSON Schema 格式的参数定义
            
        Returns:
            装饰器函数
            
        Example:
            @tool_registry.register(
                name="web_search",
                description="搜索网页获取信息",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"}
                    },
                    "required": ["query"]
                }
            )
            async def web_search(query: str) -> Dict[str, Any]:
                ...
        """
        def decorator(func: Callable) -> Callable:
            self._tools[name] = Tool(
                name=name,
                description=description,
                parameters=parameters,
                function=func
            )
            return func
        return decorator
    
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
