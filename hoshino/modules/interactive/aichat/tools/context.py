"""
AI Tool 调用上下文管理
提供 ContextVars 用于 Session 自动注入

注意：图片提取功能已移至 Session 类的方法：
- session.get_images() - 获取所有图片
- session.get_image_by_index(index) - 按索引获取图片
"""
import contextvars
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from ..session import Session

# 当前工具调用的上下文
tool_call_context: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    'tool_call_context', default=None
)


def get_current_context() -> Optional[Dict[str, Any]]:
    """获取当前工具调用上下文"""
    return tool_call_context.get()


def get_current_session() -> Optional["Session"]:
    """
    获取当前工具调用上下文中的 session
    
    Returns:
        Session 对象或 None
    """
    ctx = tool_call_context.get()
    if ctx:
        return ctx.get('session')
    return None
