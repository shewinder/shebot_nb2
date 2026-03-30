"""
AI Tool: 服务管理
支持查看、启用、禁用机器人服务

【安全限制】
- 仅群管理员、群主或超级用户可使用此工具
- 只能操作当前所在群组的服务（禁止跨群操作）
"""
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from loguru import logger

from ..registry import tool_registry, ok, fail
from hoshino.service import Service, _loaded_services
from hoshino.permission import SUPERUSER, GROUP_ADMIN, GROUP_OWNER

if TYPE_CHECKING:
    from hoshino import Bot, Event


async def _check_permission(bot: "Bot", event: "Event") -> bool:
    """
    检查用户是否有权限管理服务
    
    权限要求：群管理员、群主或超级用户
    
    Args:
        bot: Bot 实例
        event: 事件对象
        
    Returns:
        是否有权限
    """
    # 超级用户始终有权限
    is_superuser = await SUPERUSER(bot, event)
    if is_superuser:
        return True
    
    # 检查是否是群聊
    if not hasattr(event, 'group_id') or not event.group_id:
        return False
    
    # 检查是否是群管理员或群主
    is_admin = await GROUP_ADMIN(bot, event)
    is_owner = await GROUP_OWNER(bot, event)
    
    return is_admin or is_owner


def _is_group_context(event: Optional["Event"]) -> bool:
    """检查是否在群聊上下文中"""
    if not event:
        return False
    return hasattr(event, 'group_id') and event.group_id is not None


@tool_registry.register(
    name="manage_service",
    description="""管理机器人的服务功能。可以查看服务列表、启用或禁用服务。

## 权限要求
- 仅群管理员、群主或超级用户可使用此工具
- 普通用户无法调用此工具

## 支持的操作
- list: 列出所有服务及其状态
- enable: 在指定群启用某个服务
- disable: 在指定群禁用某个服务
- status: 查看指定服务的详细状态

## 使用示例
1. 列出所有服务: action="list"
2. 启用服务: action="enable", service_name="aichat"
3. 禁用服务: action="disable", service_name="setu"
4. 查看服务状态: action="status", service_name="aichat"

## 安全限制
- 只能操作当前所在群组的服务（group_id 自动从当前上下文获取）
- 不允许通过 AI 工具跨群操作其他群的服务
- 服务名模糊匹配时如果有多个匹配结果，会返回错误而不会自动执行

注意：此工具仅在群聊中可用，私聊场景下无法使用。""",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型: list/enable/disable/status",
                "enum": ["list", "enable", "disable", "status"]
            },
            "service_name": {
                "type": "string",
                "description": "服务名称，enable/disable/status 时必需"
            }
        },
        "required": ["action"]
    }
)
async def manage_service(
    action: str,
    service_name: str = "",
    bot: Optional["Bot"] = None,
    event: Optional["Event"] = None,
) -> Dict[str, Any]:
    """
    服务管理工具
    
    【重要】权限要求：仅群管理员、群主或超级用户可使用
    
    Args:
        action: 操作类型
        service_name: 服务名称
        bot: Bot 实例（自动注入）
        event: 事件对象（自动注入）
    
    Returns:
        操作结果
    """
    
    # ====== 权限检查 ======
    if not bot or not event:
        return fail(
            "无法获取必要的上下文信息",
            error="Missing bot or event context"
        )
    
    has_permission = await _check_permission(bot, event)
    if not has_permission:
        return fail(
            "权限不足：仅群管理员、群主或超级用户可管理服务",
            error="Permission denied"
        )
    
    # ====== 群聊上下文检查 ======
    if not _is_group_context(event):
        return fail(
            "此工具仅在群聊中可用，私聊场景无法管理服务",
            error="Not in group context"
        )
    
    # 获取当前群号（禁止跨群操作）
    current_group_id = getattr(event, 'group_id', None)
    if not current_group_id:
        return fail(
            "无法获取当前群号",
            error="Missing group_id"
        )
    
    action = action.lower().strip()
    
    try:
        if action == "list":
            return _list_services(current_group_id)
        
        elif action == "enable":
            return _enable_service(service_name, current_group_id, require_exact_match=True)
        
        elif action == "disable":
            return _disable_service(service_name, current_group_id, require_exact_match=True)
        
        elif action == "status":
            return _service_status(service_name, current_group_id)
        
        else:
            return fail(f"未知操作: {action}。支持: list/enable/disable/status", error="Invalid action")
    
    except Exception as e:
        logger.exception(f"manage_service 执行失败: {e}")
        return fail(f"操作失败: {str(e)}", error=str(e))


def _list_services(group_id: int) -> Dict[str, Any]:
    """列出所有服务"""
    
    services = Service.get_loaded_services()
    
    if not services:
        return ok("当前没有加载任何服务", metadata={"count": 0})
    
    # 分类服务
    visible_services: List[tuple] = []
    hidden_services: List[str] = []
    
    for name, sv in services.items():
        if sv.visible:
            # 检查在当前群的启用状态
            if sv.check_enabled(group_id):
                status = "🟢 已启用"
            else:
                status = "⚪ 已禁用"
            visible_services.append((name, sv, status))
        else:
            hidden_services.append(name)
    
    # 按名称排序
    visible_services.sort(key=lambda x: x[0])
    hidden_services.sort()
    
    lines = [f"📋 机器人服务列表（共 {len(services)} 个）\n"]
    
    if visible_services:
        lines.append("【可见服务】")
        for name, sv, status in visible_services:
            help_text = sv.help or "无描述"
            # 截断过长的帮助文本
            if len(help_text) > 50:
                help_text = help_text[:50] + "..."
            
            lines.append(f"• {name} {status}")
            lines.append(f"  {help_text}")
            lines.append("")
    
    if hidden_services:
        lines.append(f"\n【隐藏服务】({len(hidden_services)} 个)")
        lines.append(", ".join(hidden_services))
    
    lines.append(f"\n💡 当前操作群: {group_id}")
    lines.append("使用「manage_service enable service_name=xxx」启用服务")
    lines.append("使用「manage_service disable service_name=xxx」禁用服务")
    
    return ok(
        "\n".join(lines),
        metadata={
            "count": len(services),
            "visible_count": len(visible_services),
            "hidden_count": len(hidden_services),
            "services": list(services.keys()),
            "group_id": group_id
        }
    )


def _enable_service(service_name: str, group_id: int, require_exact_match: bool = True) -> Dict[str, Any]:
    """
    在指定群启用服务
    
    Args:
        service_name: 服务名称
        group_id: 群号
        require_exact_match: 是否要求精确匹配（安全选项）
    """
    
    if not service_name:
        return fail("请提供服务名称，使用 manage_service list 查看可用服务", error="Missing service_name")
    
    services = Service.get_loaded_services()
    
    # 精确匹配
    if service_name in services:
        sv = services[service_name]
        sv.set_enable(group_id)
        return ok(
            f"✅ 服务 '{service_name}' 已在群 {group_id} 启用",
            metadata={"service": service_name, "group_id": group_id, "enabled": True}
        )
    
    # 如果要求精确匹配，直接返回错误
    if require_exact_match:
        available = [name for name in services.keys() if service_name.lower() in name.lower()]
        if len(available) == 1:
            # 只有一个相似选项时提示用户
            return fail(
                f"未找到精确匹配的服务 '{service_name}'。\n"
                f"您是否想启用 '{available[0]}'？请使用完整名称重新尝试。",
                error="Service not found - did you mean: " + available[0]
            )
        elif len(available) > 1:
            return fail(
                f"未找到精确匹配的服务 '{service_name}'。\n"
                f"找到多个相似服务: {', '.join(available[:5])}，请使用完整名称。",
                error="Service not found - multiple matches"
            )
        else:
            return fail(
                f"未找到服务 '{service_name}'，使用 manage_service list 查看可用服务",
                error="Service not found"
            )
    
    # 尝试模糊匹配（仅当不要求精确匹配时）
    matches = [name for name in services.keys() if service_name.lower() in name.lower()]
    if len(matches) == 1:
        sv = services[matches[0]]
        sv.set_enable(group_id)
        return ok(
            f"✅ 服务 '{matches[0]}' 已在群 {group_id} 启用（匹配自 '{service_name}'）",
            metadata={"service": matches[0], "group_id": group_id, "enabled": True}
        )
    elif len(matches) > 1:
        return fail(
            f"找到多个匹配的服务: {', '.join(matches)}，请使用完整名称",
            error="Ambiguous service name"
        )
    else:
        return fail(
            f"未找到服务 '{service_name}'，使用 manage_service list 查看可用服务",
            error="Service not found"
        )


def _disable_service(service_name: str, group_id: int, require_exact_match: bool = True) -> Dict[str, Any]:
    """
    在指定群禁用服务
    
    Args:
        service_name: 服务名称
        group_id: 群号
        require_exact_match: 是否要求精确匹配（安全选项）
    """
    
    if not service_name:
        return fail("请提供服务名称，使用 manage_service list 查看可用服务", error="Missing service_name")
    
    services = Service.get_loaded_services()
    
    # 精确匹配
    if service_name in services:
        sv = services[service_name]
        sv.set_disable(group_id)
        return ok(
            f"⛔ 服务 '{service_name}' 已在群 {group_id} 禁用",
            metadata={"service": service_name, "group_id": group_id, "enabled": False}
        )
    
    # 如果要求精确匹配，直接返回错误
    if require_exact_match:
        available = [name for name in services.keys() if service_name.lower() in name.lower()]
        if len(available) == 1:
            # 只有一个相似选项时提示用户
            return fail(
                f"未找到精确匹配的服务 '{service_name}'。\n"
                f"您是否想禁用 '{available[0]}'？请使用完整名称重新尝试。",
                error="Service not found - did you mean: " + available[0]
            )
        elif len(available) > 1:
            return fail(
                f"未找到精确匹配的服务 '{service_name}'。\n"
                f"找到多个相似服务: {', '.join(available[:5])}，请使用完整名称。",
                error="Service not found - multiple matches"
            )
        else:
            return fail(
                f"未找到服务 '{service_name}'，使用 manage_service list 查看可用服务",
                error="Service not found"
            )
    
    # 尝试模糊匹配（仅当不要求精确匹配时）
    matches = [name for name in services.keys() if service_name.lower() in name.lower()]
    if len(matches) == 1:
        sv = services[matches[0]]
        sv.set_disable(group_id)
        return ok(
            f"⛔ 服务 '{matches[0]}' 已在群 {group_id} 禁用（匹配自 '{service_name}'）",
            metadata={"service": matches[0], "group_id": group_id, "enabled": False}
        )
    elif len(matches) > 1:
        return fail(
            f"找到多个匹配的服务: {', '.join(matches)}，请使用完整名称",
            error="Ambiguous service name"
        )
    else:
        return fail(
            f"未找到服务 '{service_name}'，使用 manage_service list 查看可用服务",
            error="Service not found"
        )


def _service_status(service_name: str, group_id: int, require_exact_match: bool = True) -> Dict[str, Any]:
    """
    查看服务状态
    
    Args:
        service_name: 服务名称
        group_id: 群号
        require_exact_match: 是否要求精确匹配（安全选项）
    """
    
    if not service_name:
        return fail("请提供服务名称", error="Missing service_name")
    
    services = Service.get_loaded_services()
    
    # 精确匹配
    sv = None
    actual_name = service_name
    
    if service_name in services:
        sv = services[service_name]
    elif not require_exact_match:
        # 尝试模糊匹配（仅当不要求精确匹配时）
        matches = [name for name in services.keys() if service_name.lower() in name.lower()]
        if len(matches) == 1:
            sv = services[matches[0]]
            actual_name = matches[0]
        elif len(matches) > 1:
            return fail(
                f"找到多个匹配的服务: {', '.join(matches)}，请使用完整名称",
                error="Ambiguous service name"
            )
    
    if not sv:
        # 查找相似服务用于提示
        available = [name for name in services.keys() if service_name.lower() in name.lower()]
        if len(available) == 1:
            return fail(
                f"未找到精确匹配的服务 '{service_name}'。\n"
                f"您是否想查看 '{available[0]}'？请使用完整名称重新尝试。",
                error="Service not found - did you mean: " + available[0]
            )
        elif len(available) > 1:
            return fail(
                f"未找到精确匹配的服务 '{service_name}'。\n"
                f"找到多个相似服务: {', '.join(available[:5])}，请使用完整名称。",
                error="Service not found - multiple matches"
            )
        else:
            return fail(
                f"未找到服务 '{service_name}'，使用 manage_service list 查看可用服务",
                error="Service not found"
            )
    
    lines = [f"📊 服务 '{actual_name}' 状态\n"]
    
    # 基本信息
    lines.append(f"名称: {sv.name}")
    lines.append(f"可见性: {'可见' if sv.visible else '隐藏'}")
    lines.append(f"默认启用: {'是' if sv.enable_on_default else '否'}")
    lines.append(f"帮助信息: {sv.help or '无'}")
    
    # 群组状态
    is_enabled = sv.check_enabled(group_id)
    lines.append(f"\n在群 {group_id} 的状态: {'🟢 已启用' if is_enabled else '⚪ 已禁用'}")
    
    # 启用/禁用统计
    lines.append(f"\n全局启用群数: {len(sv.enable_group)}")
    lines.append(f"全局禁用群数: {len(sv.disable_group)}")
    
    if sv.enable_group:
        lines.append(f"启用列表: {list(sv.enable_group)[:10]}{'...' if len(sv.enable_group) > 10 else ''}")
    if sv.disable_group:
        lines.append(f"禁用列表: {list(sv.disable_group)[:10]}{'...' if len(sv.disable_group) > 10 else ''}")
    
    # 匹配器信息
    if sv.matchers:
        lines.append(f"\n匹配器数量: {len(sv.matchers)}")
    
    return ok(
        "\n".join(lines),
        metadata={
            "service": actual_name,
            "visible": sv.visible,
            "enable_on_default": sv.enable_on_default,
            "group_id": group_id,
            "enabled_in_group": is_enabled,
            "enable_count": len(sv.enable_group),
            "disable_count": len(sv.disable_group)
        }
    )
