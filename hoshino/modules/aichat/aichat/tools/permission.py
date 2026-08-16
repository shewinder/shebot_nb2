"""
AI 工具权限管理框架

两级权限：
- SUPERUSER: 超级用户（读取配置判断）
- USER: 所有用户

双层接线（P3）：
1. schema 层：tools/access.get_available_tools 过滤无权工具的 schema（省 token）；
2. 执行层：chat_executor._execute_tool_call 执行前校验（防模型幻觉调用
   未出现在 schema 中的工具名绕过）。

默认权限表全 USER（零行为变化），管理员通过 Config.tool_permissions
覆盖，如 {"execute_script": "SUPERUSER"}。
"""
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

from loguru import logger
from hoshino import hsn_config

from ..config import Config

conf = Config.get_instance('aichat')

# 权限级别: SUPERUSER | USER
PermissionLevel = str

# 默认工具权限（默认全 USER；在 Config.tool_permissions 中覆盖收紧）
DEFAULT_TOOL_PERMISSIONS: Dict[str, PermissionLevel] = {
    "execute_script": "USER",
    "service_manage": "USER",  # 工具内部有权限校验
    "schedule_task": "USER",
    "generate_image": "USER",
    "web_search": "USER",
    "weather": "USER",
    "get_current_time": "USER",
    # skill 自更新：全局共享资源，默认仅超级用户可操作（A1 决策）
    "create_skill": "SUPERUSER",
    "update_skill": "SUPERUSER",
    "delete_skill": "SUPERUSER",
    "rollback_skill": "SUPERUSER",
    "reload_skills": "SUPERUSER",
}


def _get_superusers() -> set:
    """从配置获取超级用户列表"""
    superusers = getattr(hsn_config, 'superusers', set())
    if isinstance(superusers, (list, tuple, set)):
        return set(int(s) for s in superusers)
    return set()


def is_superuser(user_id: Optional[int]) -> bool:
    """检查是否为超级用户（读取配置）"""
    if not user_id:
        return False
    try:
        uid = int(user_id)
        return uid in _get_superusers()
    except (ValueError, TypeError):
        return False


def get_tool_permission(tool_name: str) -> PermissionLevel:
    """获取工具权限级别：Config.tool_permissions 覆盖 > 默认表 > USER"""
    return conf.tool_permissions.get(tool_name) or DEFAULT_TOOL_PERMISSIONS.get(tool_name, "USER")


def set_tool_permission(tool_name: str, level: PermissionLevel):
    """动态设置工具权限（仅内存生效，持久化需改 Config.tool_permissions）"""
    DEFAULT_TOOL_PERMISSIONS[tool_name] = level
    logger.info(f"设置工具 {tool_name} 的权限为 {level}")


def check_permission(
    level: PermissionLevel,
    user_id: Optional[int] = None,
    event: Optional[Any] = None,
    context: Optional[Dict[str, Any]] = None,
    session: Optional[Any] = None,
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
        session: 会话对象（从中提取 user_id）

    Returns:
        (是否有权限, 原因)
    """
    # USER 级别直接通过
    if level == "USER":
        return True, "user"

    uid = user_id

    if uid is None and session is not None:
        uid = getattr(session, 'user_id', None)

    if uid is None and event is not None:
        uid = getattr(event, 'user_id', None)

    if uid is None and context is not None:
        scheduled_task = context.get('scheduled_task')
        if scheduled_task:
            uid = getattr(scheduled_task, 'user_id', None)

    if not uid:
        return False, "无法获取用户信息"

    if is_superuser(uid):
        return True, "superuser"

    return False, "该功能仅超级用户可用"


def require_permission(
    level: PermissionLevel,
    error_msg: Optional[str] = None
):
    """
    权限装饰器（可选辅助，执行层校验已内建于 chat_executor，工具无需自行装饰）

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


# 快捷装饰器
superuser_only = lambda **kwargs: require_permission("SUPERUSER", **kwargs)
