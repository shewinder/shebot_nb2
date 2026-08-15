"""日志上下文与脱敏工具

约束：本模块只依赖标准库，禁止 import hoshino。

log_context / log_tag：
    用 contextvars 携带当前会话/任务标识，供日志前缀使用。
    loguru 的 contextualize 依赖 sink 格式支持 extra 字段，而本项目
    hoshino sink 格式不保证包含 extra，因此采用"渲染为前缀字符串"的
    方式，任何 sink 下都可见。

sanitize / sanitize_text：
    日志脱敏。base64 图片数据、超长内容在进入日志前必须处理，
    防止日志体积爆炸与隐私泄露。
"""
import contextvars
import re
from contextlib import contextmanager
from typing import Any, Dict, Iterator

_log_ctx: contextvars.ContextVar[Dict[str, str]] = contextvars.ContextVar(
    "aichat_log_ctx", default={}
)

# data:image/png;base64,AAAA...（≥80 个 base64 字符才视为真实图片数据）
_BASE64_BLOB_RE = re.compile(r"data:[^;\s,<>]+;base64,[A-Za-z0-9+/=]{80,}")

_BASE64_PLACEHOLDER = "[base64数据已省略]"


@contextmanager
def log_context(**fields: str) -> Iterator[None]:
    """在上下文中附加日志字段，log_tag() 会将其渲染为前缀"""
    token = _log_ctx.set(fields)
    try:
        yield
    finally:
        _log_ctx.reset(token)


def log_tag() -> str:
    """渲染当前日志上下文前缀，如 "[session=xxx][agent=sub]"；无上下文时为空串"""
    ctx = _log_ctx.get()
    if not ctx:
        return ""
    return "[" + "][".join(f"{k}={v}" for k, v in ctx.items()) + "]"


def sanitize_text(text: str, max_len: int = 2000) -> str:
    """替换 base64 数据块并截断超长文本"""
    text = _BASE64_BLOB_RE.sub(_BASE64_PLACEHOLDER, text)
    if len(text) > max_len:
        return text[:max_len] + f"...[截断 {len(text) - max_len} 字符]"
    return text


def sanitize(obj: Any, max_len: int = 2000) -> Any:
    """递归脱敏：dict/list 逐层处理，str 走 sanitize_text，其余类型原样返回"""
    if isinstance(obj, dict):
        return {k: sanitize(v, max_len) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(item, max_len) for item in obj]
    if isinstance(obj, tuple):
        return tuple(sanitize(item, max_len) for item in obj)
    if isinstance(obj, str):
        return sanitize_text(obj, max_len)
    return obj
