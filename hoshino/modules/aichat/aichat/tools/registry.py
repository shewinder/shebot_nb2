import inspect
import re
from enum import Enum
from functools import lru_cache
from types import UnionType
from typing import (
    Annotated,
    Any,
    Callable,
    Dict,
    ForwardRef,
    List,
    Literal,
    Optional,
    Tuple,
    TypedDict,
    Union,
    get_args,
    get_origin,
)

from loguru import logger
from annotated_types import Ge, Gt, Le, Lt, MaxLen, MinLen
from pydantic import BaseModel, ConfigDict
from pydantic.fields import FieldInfo

# 基础类型 → JSON Schema type 映射
_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    dict: "object",
    list: "array",
}

# future annotations 下内置类型名的字符串映射
_STR_TYPE_MAP = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "dict": dict,
    "list": list,
}


class ToolResult(TypedDict, total=False):
    """工具返回结果标准格式

    使用辅助函数 ok() 和 fail() 创建，避免手写重复字典

    媒体标识符是给 AI 和工具使用的内部句柄。只有回复中的显式
    [[send_image:ai_image_1]] / [[send_video:ai_video_1]] 标记会发送媒体。

    Example:
        return ok("图片已生成，内部句柄：<ai_image_1>", metadata={"id": 1})
        return fail("API 调用失败")
    """
    success: bool
    content: str
    error: Optional[str]
    metadata: Dict[str, Any]


def ok(content: str, metadata: Optional[Dict[str, Any]] = None) -> ToolResult:
    """创建成功的工具返回结果

    Args:
        content: 给 AI 看的结果描述。媒体句柄应作为内部引用返回，是否发送
            由 AI 在回复中使用显式 [[send_*:句柄]] 标记决定。
        metadata: 额外元数据（可选）

    Returns:
        ToolResult 字典

    Example:
        # 返回内部句柄，是否发送由显式发送标记决定
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
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    parameters: Dict[str, Any]
    function: Callable
    # Pydantic 输入模型模式：签名中唯一的 BaseModel 参数（schema 自动生成 + 执行前校验）
    input_model: Optional[Any] = None
    input_param: Optional[str] = None


# ========== Schema 自动推导 ==========


def _extract_annotated(ann: Any) -> Tuple[Any, Optional[str]]:
    """Annotated[T, ...] → (T, description)；无 Annotated 原样返回"""
    if get_origin(ann) is Annotated:
        args = get_args(ann)
        desc: Optional[str] = None
        for meta in args[1:]:
            if isinstance(meta, FieldInfo):
                desc = meta.description
            elif isinstance(meta, str) and desc is None:
                desc = meta
        return args[0], desc
    return ann, None


def _unwrap_optional(ann: Any) -> Tuple[Any, bool]:
    """剥离 Optional[T]/T|None（含字符串形式 "T | None"），返回 (inner, was_optional)"""
    # future annotations 下整个注解是字符串，如 "Session | None"
    if isinstance(ann, str) and "|" in ann:
        parts = [p.strip() for p in ann.split("|")]
        non_none = [p for p in parts if p != "None"]
        if len(non_none) == 1:
            return non_none[0], True
        return ann, False
    origin = get_origin(ann)
    if origin in (Union, UnionType):
        args = [a for a in get_args(ann) if a is not type(None)]
        if len(args) == 1:
            return args[0], True
    return ann, False


def _inline_defs(schema: Dict[str, Any]) -> Dict[str, Any]:
    """把 $defs/$ref 递归内联展开（部分供应商的 tool schema 不支持跨引用）"""
    defs = schema.get("$defs", {})
    if not defs:
        return schema

    def _resolve(node: Any, stack: frozenset) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref", "")
            if ref.startswith("#/$defs/"):
                name = ref.rsplit("/", 1)[-1]
                if name in defs and name not in stack:
                    return _resolve(defs[name], stack | {name})
                return {}
            return {k: _resolve(v, stack) for k, v in node.items()}
        if isinstance(node, list):
            return [_resolve(item, stack) for item in node]
        return node

    result = dict(schema)
    result.pop("$defs", None)
    return _resolve(result, frozenset())


def _constraints_from_annotated(ann: Any) -> Dict[str, Any]:
    """从 Annotated 元数据提取数值/长度约束 → JSON Schema 关键字"""
    constraints: Dict[str, Any] = {}
    if get_origin(ann) is not Annotated:
        return constraints
    for meta in get_args(ann)[1:]:
        if not isinstance(meta, FieldInfo):
            continue
        for item in meta.metadata:
            if isinstance(item, Ge):
                constraints["minimum"] = item.ge
            elif isinstance(item, Le):
                constraints["maximum"] = item.le
            elif isinstance(item, Gt):
                constraints["exclusiveMinimum"] = item.gt
            elif isinstance(item, Lt):
                constraints["exclusiveMaximum"] = item.lt
            elif isinstance(item, MinLen):
                constraints["minLength"] = item.min_length
            elif isinstance(item, MaxLen):
                constraints["maxLength"] = item.max_length
    return constraints


def _annotation_to_schema(ann: Any) -> Dict[str, Any]:
    """单个类型注解 → JSON Schema 片段"""
    if ann is None or ann is inspect.Parameter.empty or ann is Any:
        return {}

    constraints = _constraints_from_annotated(ann)
    base, _ = _extract_annotated(ann)
    base, _ = _unwrap_optional(base)

    # future annotations 下的内置类型名字符串（如 "str"、"int"）
    if isinstance(base, str):
        base = _STR_TYPE_MAP.get(base, base)

    origin = get_origin(base)
    schema: Dict[str, Any]
    if origin is Literal:
        values = list(get_args(base))
        schema = {"enum": values}
        # 推断字面量类型（全部同型时补 type，与手写 schema 保持一致）
        if values and all(type(v) is type(values[0]) for v in values):
            lit_type = _TYPE_MAP.get(type(values[0]))
            if lit_type:
                schema = {"type": lit_type, "enum": values}
    elif isinstance(base, type) and issubclass(base, Enum):
        schema = {"type": "string", "enum": [e.value for e in base]}
    elif isinstance(base, type) and issubclass(base, BaseModel):
        schema = base.model_json_schema()
        schema.pop("title", None)
        schema = _inline_defs(schema)
    elif origin is list:
        item_ann = get_args(base)[0] if get_args(base) else Any
        schema = {"type": "array", "items": _annotation_to_schema(item_ann)}
    elif origin is dict:
        args = get_args(base)
        value_schema = _annotation_to_schema(args[1]) if len(args) == 2 else {}
        schema = {"type": "object", "additionalProperties": value_schema}
    else:
        type_name = _TYPE_MAP.get(base)
        schema = {"type": type_name} if type_name else {}

    schema.update(constraints)
    return schema


def _parse_param_docs(docstring: Optional[str]) -> Dict[str, str]:
    """从 docstring 解析 ':param name: 描述' 行（Google 风格）"""
    docs: Dict[str, str] = {}
    if not docstring:
        return docs
    pattern = re.compile(r"^\s*:param\s+(\w+)\s*:\s*(.*)$")
    for line in docstring.splitlines():
        m = pattern.match(line)
        if m and m.group(2).strip():
            docs[m.group(1)] = m.group(2).strip()
    return docs


def _build_schema_from_signature(func: Callable) -> Dict[str, Any]:
    """从函数签名自动生成 OpenAI tool schema

    - 默认值存在或 Optional → 非必填
    - Session/Bot/Event 注入参数自动排除
    - 参数描述：Annotated[...] > docstring :param > 无
    """
    injectable = get_injectable_params(func)
    param_docs = _parse_param_docs(func.__doc__)
    properties: Dict[str, Any] = {}
    required: List[str] = []

    for pname, param in inspect.signature(func).parameters.items():
        if pname in injectable:
            continue
        ann = param.annotation
        schema = _annotation_to_schema(ann)
        base, annotated_desc = _extract_annotated(ann)
        _, optional = _unwrap_optional(base)
        desc = annotated_desc or param_docs.get(pname)
        if desc:
            schema["description"] = desc
        properties[pname] = schema
        if param.default is inspect.Parameter.empty and not optional:
            required.append(pname)

    return {"type": "object", "properties": properties, "required": required}


def _detect_input_model(func: Callable) -> Tuple[Optional[str], Optional[type]]:
    """检测签名中唯一的 BaseModel 参数（Pydantic 输入模型模式），返回 (参数名, 模型类)"""
    for pname, param in inspect.signature(func).parameters.items():
        ann, _ = _extract_annotated(param.annotation)
        ann, _ = _unwrap_optional(ann)
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            return pname, ann
    return None, None


def _first_paragraph(docstring: Optional[str]) -> str:
    """docstring 首个非空段落（作为默认工具描述）"""
    if not docstring:
        return ""
    parts = [p.strip() for p in docstring.split("\n\n") if p.strip()]
    return parts[0] if parts else docstring.strip()


class ToolRegistry:
    """
    工具注册器 - 管理所有 AI 可调用工具

    推荐用法（schema 自动生成，禁止手写 parameters）：
        @tool_registry.register(description="查询天气")
        async def get_weather(city: Annotated[str, Field(description="城市名")]):
            ...

    复杂校验场景用 Pydantic 输入模型：
        class GetWeatherInput(BaseModel):
            city: str = Field(description="城市名")

        @tool_registry.register
        async def get_weather(params: GetWeatherInput):
            ...

    参数注入：
        工具函数的参数如果声明为 Session、Bot 或 Event 类型，
        将在调用时自动注入（如果该参数未由 AI 提供）。
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(
        self,
        func: Optional[Callable] = None,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Callable[[Callable], Callable]:
        """
        装饰器：注册一个工具

        Args:
            name: 工具名称（缺省取函数名）
            description: 工具描述（缺省取 docstring 首段）
            parameters: JSON Schema（缺省自动从签名/Pydantic 模型生成；
                        仅特殊场景手写）
        """
        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or _first_paragraph(func.__doc__)
            input_param, input_model = (None, None)
            schema = parameters
            if schema is None:
                input_param, input_model = _detect_input_model(func)
                if input_model is not None:
                    raw = input_model.model_json_schema()
                    raw.pop("title", None)
                    schema = _inline_defs(raw)
                else:
                    schema = _build_schema_from_signature(func)
            self._tools[tool_name] = Tool(
                name=tool_name,
                description=tool_desc,
                parameters=schema,
                function=func,
                input_model=input_model,
                input_param=input_param,
            )
            return func
        if func is not None:
            return decorator(func)
        return decorator

    def get_schemas(self) -> List[Dict[str, Any]]:
        """
        获取所有已注册工具的 OpenAI 格式 schema

        Returns:
            OpenAI tools 格式的列表
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            }
            for tool in self._tools.values()
        ]

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


@lru_cache(maxsize=None)
def get_injectable_params(func: Callable) -> Dict[str, str]:
    """
    分析函数签名，返回需要注入的参数映射（结果按函数缓存）

    支持以下类型注解格式：
    - Session / Optional[Session] / Optional["Session"] / "Session" | None
    - Bot / Optional[Bot] / Optional["Bot"]
    - Event / Optional[Event] / Optional["Event"]

    Args:
        func: 要分析的函数

    Returns:
        {参数名: 类型名} 的字典，如 {'session': 'Session', 'bot': 'Bot'}
    """
    sig = inspect.signature(func)
    injectable: Dict[str, str] = {}

    INJECTABLE_TYPES = {'Session', 'Bot', 'Event'}

    for param_name, param in sig.parameters.items():
        ann = param.annotation

        if ann is inspect.Parameter.empty:
            continue

        # Annotated[T, ...] 先剥离，再统一经 _unwrap_optional 剥离 Optional/|None
        if get_origin(ann) is Annotated:
            ann = get_args(ann)[0]
        ann, _ = _unwrap_optional(ann)

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
