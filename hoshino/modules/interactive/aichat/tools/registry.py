import inspect
from typing import Any, Callable, Dict, List, Optional, ForwardRef, TypedDict

from pydantic import BaseModel


class ToolResult(TypedDict, total=False):
    """工具返回结果标准格式
    
    使用辅助函数 ok() 和 fail() 创建，避免手写重复字典
    
    图片发送机制：在 content 中包含图片标识符（如 <ai_image_1>），
    系统会自动识别并发送对应图片。
    
    Example:
        return ok("图片已生成 <ai_image_1>", metadata={"id": 1})
        return fail("API 调用失败")
    """
    success: bool
    content: str
    error: Optional[str]
    metadata: Dict[str, Any]


def ok(content: str, metadata: Optional[Dict[str, Any]] = None) -> ToolResult:
    """创建成功的工具返回结果
    
    Args:
        content: 给 AI 看的结果描述。如需发送图片，请在 content 中包含标识符
                （如 "已生成图片 <ai_image_1>"），系统会自动识别并发送。
        metadata: 额外元数据（可选）
        
    Returns:
        ToolResult 字典
        
    Example:
        # 在 content 中包含标识符来发送图片
        return ok("已成功生成图片 <ai_image_1>")
        
        # 多个图片
        return ok("生成了两张图片：<ai_image_1> 和 <ai_image_2>")
        
        # 带元数据
        return ok("任务已创建", metadata={"task_id": "xxx"})
    """
    return {
        "success": True,
        "content": content,
        "error": None,
        "metadata": metadata or {}
    }


def fail(content: str, error: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> ToolResult:
    """创建失败的工具返回结果
    
    Args:
        content: 给 AI 看的错误描述
        error: 技术错误信息（可选，默认使用 content）
        metadata: 额外元数据（可选）
        
    Returns:
        ToolResult 字典
        
    Example:
        return fail("未找到图片模型")
        return fail("API 调用失败", error="HTTP 500")
    """
    return {
        "success": False,
        "content": content,
        "images": [],
        "error": error or content,
        "metadata": metadata or {}
    }


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
    
    参数注入：
        工具函数的参数如果声明为 Session、Bot 或 Event 类型，
        将在调用时自动注入（如果该参数未由 AI 提供）
    """
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
    
    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
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
                parameters={...}
            )
            async def web_search(query: str) -> Dict[str, Any]:
                ...
            
            @tool_registry.register(
                name="edit_image",
                description="编辑图片",
                parameters={...}
            )
            async def edit_image(
                prompt: str,
                session: Optional["Session"] = None  # 自动注入
            ):
                ...
        """
        def decorator(func: Callable) -> Callable:
            self._tools[name] = Tool(
                name=name,
                description=description,
                parameters=parameters,
                function=func,
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


def get_injectable_params(func: Callable) -> Dict[str, str]:
    """
    分析函数签名，返回需要注入的参数映射
    
    支持以下类型注解格式：
    - Session / Optional[Session] / Optional["Session"]
    - Bot / Optional[Bot] / Optional["Bot"]  
    - Event / Optional[Event] / Optional["Event"]
    
    Args:
        func: 要分析的函数
        
    Returns:
        {参数名: 类型名} 的字典，如 {'session': 'Session', 'bot': 'Bot'}
    """
    from typing import get_origin, get_args, Union
    
    sig = inspect.signature(func)
    injectable: Dict[str, str] = {}
    
    INJECTABLE_TYPES = {'Session', 'Bot', 'Event'}
    
    for param_name, param in sig.parameters.items():
        ann = param.annotation
        
        if ann is inspect.Parameter.empty:
            continue
        
        # 处理 Optional[T] / Union[T, None]
        origin = get_origin(ann)
        if origin is Union:
            args = get_args(ann)
            # 取第一个非 NoneType 的参数
            for arg in args:
                if arg is not type(None):
                    ann = arg
                    break
        
        # 提取类型名称
        type_name = _extract_type_name(ann)
        if type_name in INJECTABLE_TYPES:
            injectable[param_name] = type_name
    
    return injectable


def _extract_type_name(tp: Any) -> Optional[str]:
    """
    从类型注解中提取类型名称（支持 Optional, ForwardRef, 字符串前向引用）
    
    Args:
        tp: 类型注解
        
    Returns:
        类型名称字符串，如 'Session'、'Bot'，无法识别则返回 None
    """
    if tp is None:
        return None
    
    # 处理字符串前向引用（如 "Session"）
    if isinstance(tp, str):
        return tp
    
    # 处理 ForwardRef('Session')
    if isinstance(tp, ForwardRef):
        return tp.__forward_arg__
    
    # 处理实际类型
    if hasattr(tp, '__name__'):
        return tp.__name__
    
    return None
