"""
AI 工具权限管理框架

简化设计：仅两种权限级别
- SUPERUSER: 超级用户（读取配置判断）
- USER: 所有用户

使用示例:
    @tool_registry.register(...)
    @require_permission("SUPERUSER")
    async def broadcast(...):
        ...
"""
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

from loguru import logger
from hoshino import hsn_config

# 权限级别: SUPERUSER | USER
PermissionLevel = str

# 工具权限配置
DEFAULT_TOOL_PERMISSIONS: Dict[str, PermissionLevel] = {
    # 超级用户专属
    
    # 所有人可用
    "execute_script": "USER",
    "service_manage": "USER", # 工具内部有权限校验
    "schedule_task": "USER",
    "generate_image": "USER",
    "web_search": "USER",
    "weather": "USER",
    "get_current_time": "USER",
}


def _get_superusers() -> set:
    """从配置获取超级用户列表"""
    superusers = getattr(hsn_config, 'superusers', set())
    if isinstance(superusers, (list, tuple, set)):
        return set(int(s) for s in superusers)
    return set()


def _is_superuser(user_id: int) -> bool:
    """检查是否为超级用户（读取配置）"""
    if not user_id:
        return False
    try:
        uid = int(user_id)
        return uid in _get_superusers()
    except (ValueError, TypeError):
        return False


def check_permission(
    level: PermissionLevel,
    user_id: Optional[int] = None,
    event: Optional[Any] = None,
    context: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str]:
    """
    权限检查
    
    SUPERUSER: 检查 user_id 是否在配置中
    USER: 始终通过
    
    Args:
        level: 权限级别 ("SUPERUSER" | "USER")
        user_id: 用户ID（优先）
        event: 事件对象（从中提取 user_id）
        context: 上下文（定时任务场景，提取 scheduled_task.user_id）
    
    Returns:
        (是否有权限, 原因)
    """
    # USER 级别直接通过
    if level == "USER":
        return True, "user"
    
    # SUPERUSER 级别：获取 user_id 并检查
    uid = user_id
    
    if uid is None and event:
        uid = getattr(event, 'user_id', None)
    
    if uid is None and context:
        scheduled_task = context.get('scheduled_task')
        if scheduled_task:
            uid = getattr(scheduled_task, 'user_id', None)
    
    if not uid:
        return False, "无法获取用户信息"
    
    if _is_superuser(uid):
        return True, "superuser"
    
    return False, "该功能仅超级用户可用"


def require_permission(
    level: PermissionLevel,
    error_msg: Optional[str] = None
):
    """
    权限装饰器
    
    Args:
        level: "SUPERUSER" 或 "USER"
        error_msg: 自定义错误消息
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            has_perm, reason = check_permission(
                level,
                event=kwargs.get('event'),
                context=kwargs.get('context')
            )
            
            if not has_perm:
                from .registry import fail
                msg = error_msg or reason
                return fail(msg, error=f"Permission denied: {level}")
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def get_tool_permission(tool_name: str) -> PermissionLevel:
    """获取工具的权限级别"""
    return DEFAULT_TOOL_PERMISSIONS.get(tool_name, "USER")


def set_tool_permission(tool_name: str, level: PermissionLevel):
    """动态设置工具权限"""
    DEFAULT_TOOL_PERMISSIONS[tool_name] = level
    logger.info(f"设置工具 {tool_name} 的权限为 {level}")


# 快捷装饰器
superuser_only = lambda **kwargs: require_permission("SUPERUSER", **kwargs)
