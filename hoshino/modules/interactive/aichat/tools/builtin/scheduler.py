"""
AI Tool: 定时任务管理
支持创建、查看、删除、暂停/恢复定时任务
"""
from typing import Any, Dict, Optional, TYPE_CHECKING
from loguru import logger

from ..registry import tool_registry
from ...scheduler_core import scheduler_manager, generate_task_summary

if TYPE_CHECKING:
    from hoshino import Event
    from ...session import Session


@tool_registry.register(
    name="schedule_task",
    description="""创建或管理定时任务。让用户可以设定未来某个时间自动执行的任务。

## 支持的操作
- create: 创建新任务（需要 task_description 和时间参数）
- list: 查看用户的所有任务
- delete: 删除指定任务（需要 task_id）
- pause: 暂停指定任务（需要 task_id）
- resume: 恢复指定任务（需要 task_id）

## 任务类型
### 1. 循环任务（使用 cron 表达式）
适合定期执行的任务，如"每天早上8点"。

生成标准5字段 cron 表达式: minute hour day month day_of_week
- minute: 分钟 (0-59 或 *)，如 "8点整" → "0"
- hour: 小时 (0-23 或 *)，如 "早上8点" → "8"，"晚上8点" → "20"
- day: 日期 (1-31 或 *)，每天用 "*"
- month: 月份 (1-12 或 *)，每月用 "*"
- day_of_week: 星期 (0-6 或 *, 0=周日, 1=周一)，每天用 "*"

**循环任务示例：**
- "每天8点" → minute="0", hour="8", day="*", month="*", day_of_week="*"
- "每周一早上9点" → minute="0", hour="9", day="*", month="*", day_of_week="1"
- "每30分钟" → minute="*/30", hour="*", day="*", month="*", day_of_week="*"

### 2. 一次性任务（使用 one_time 参数）
适合只执行一次的任务，如"30分钟后提醒我"。
- one_time=true 表示任务只执行一次，执行后自动删除
- delay_minutes: 相对时间，如 "30分钟后" → delay_minutes=30
- execute_at: 绝对时间，ISO8601格式，如 "2024-12-25T08:00:00"

**一次性任务示例：**
- "30分钟后提醒我该开会了" → one_time=true, delay_minutes=30
- "5分钟后发送一条消息" → one_time=true, delay_minutes=5
- "明天早上8点叫我起床" → one_time=true, execute_at="2024-12-25T08:00:00"

## silent 参数说明（重要）
控制任务执行时是否添加"任务报告"框架：

- silent=false（默认）: 执行结果会包装在 "📋 定时任务执行结果\n任务: xxx\n\n[内容]" 中
- silent=true: 直接发送执行结果，不添加报告框架

## mention_user 参数说明
控制任务执行时是否 @ 任务创建者：

- mention_user=false（默认）: 正常发送消息
- mention_user=true: 在消息开头 @ 任务创建者（仅在群聊中有效）

**使用建议：**
- 个人提醒类任务 → mention_user=true, silent=true（直接 @你 + 提醒内容）
- 群公告类任务 → mention_user=false, silent=false（带报告框架，不@个人）
- 搜索/报告类任务 → mention_user=false, silent=false

**示例：**
- "30分钟后提醒我该开会了，要@我" → mention_user=true, silent=true, delay_minutes=30

任务创建后，到时间会调用AI自动执行，可以链式调用其他工具完成复杂任务。""",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型: create/list/delete/pause/resume",
                "enum": ["create", "list", "delete", "pause", "resume"]
            },
            "task_description": {
                "type": "string",
                "description": "任务描述，说明要执行什么操作。create 时必需。例如: '搜索AI新闻并生成摘要'"
            },
            "minute": {
                "type": "string",
                "description": "cron 分钟字段 (0-59, *, 或 */n)。create 时必需。如: '0', '30', '*', '*/30'"
            },
            "hour": {
                "type": "string",
                "description": "cron 小时字段 (0-23 或 *)。create 时必需。如: '8', '20', '*'"
            },
            "day": {
                "type": "string",
                "description": "cron 日期字段 (1-31 或 *)。create 时必需。通常用 '*'"
            },
            "month": {
                "type": "string",
                "description": "cron 月份字段 (1-12 或 *)。create 时必需。通常用 '*'"
            },
            "day_of_week": {
                "type": "string",
                "description": "cron 星期字段 (0-6, *, 或多值如 '1,3,5')。0=周日,1=周一。create 时必需。如: '*','1','1,3,5'"
            },
            "task_id": {
                "type": "string",
                "description": "任务ID，delete/pause/resume 操作时必需。从 list 操作的结果中获取。"
            },
            "silent": {
                "type": "boolean",
                "description": "【重要】是否静默执行（不添加任务报告框架）。必须根据任务类型判断：问候/提醒/打招呼类任务设为 true；搜索/生成/查询/报告类任务设为 false。"
            },
            "one_time": {
                "type": "boolean",
                "description": "是否为一次性任务，true表示任务只执行一次后自动删除。create时使用。"
            },
            "execute_at": {
                "type": "string",
                "description": "一次性任务的执行时间，ISO8601格式，如 '2024-12-25T08:00:00'。one_time=true时与delay_minutes二选一。"
            },
            "delay_minutes": {
                "type": "integer",
                "description": "延迟多少分钟后执行，如 30 表示30分钟后。one_time=true时与execute_at二选一，优先使用delay_minutes。"
            },
            "mention_user": {
                "type": "boolean",
                "description": "执行时是否 @ 任务创建者。适合提醒类任务，如'30分钟后提醒我'时设为 true，会在消息开头 @ 创建者。仅在群聊中有效。"
            }
        },
        "required": ["action"]
    }
)
async def schedule_task(
    action: str,
    task_description: str = "",
    minute: str = "",
    hour: str = "",
    day: str = "",
    month: str = "",
    day_of_week: str = "",
    task_id: str = "",
    silent: Optional[bool] = None,
    one_time: Optional[bool] = None,
    execute_at: str = "",
    delay_minutes: int = 0,
    mention_user: Optional[bool] = None,
    session: Optional["Session"] = None,
    event: Optional["Event"] = None,
) -> Dict[str, Any]:
    """
    定时任务管理工具
    
    Args:
        action: 操作类型
        task_description: 任务描述
        minute: cron 分钟
        hour: cron 小时
        day: cron 日期
        month: cron 月份
        day_of_week: cron 星期
        task_id: 任务ID
        session: 会话对象（自动注入）
        event: 事件对象（自动注入）
    
    Returns:
        操作结果
    """
    
    # 获取用户信息
    user_id = None
    group_id = None
    
    if event:
        user_id = getattr(event, 'user_id', None)
        group_id = getattr(event, 'group_id', None)
    
    if not user_id and session:
        session_id = getattr(session, 'session_id', '')
        if 'user_' in session_id:
            try:
                user_id = int(session_id.split('user_')[-1].split('_')[0])
            except (ValueError, IndexError):
                pass
    
    if not user_id:
        return {
            "success": False,
            "content": "无法获取用户信息，创建任务失败",
            "images": [],
            "error": "Missing user context",
            "metadata": {}
        }
    
    action = action.lower().strip()
    
    try:
        if action == "create":
            return await _create_task(
                user_id=user_id,
                group_id=group_id,
                task_description=task_description,
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
                silent=silent,
                one_time=one_time,
                execute_at=execute_at,
                delay_minutes=delay_minutes,
                mention_user=mention_user
            )
        
        elif action == "list":
            return _list_tasks(user_id)
        
        elif action == "delete":
            return _delete_task(user_id, task_id)
        
        elif action == "pause":
            return _pause_task(user_id, task_id)
        
        elif action == "resume":
            return _resume_task(user_id, task_id)
        
        else:
            return {
                "success": False,
                "content": f"未知操作: {action}。支持: create/list/delete/pause/resume",
                "images": [],
                "error": "Invalid action",
                "metadata": {}
            }
    
    except Exception as e:
        logger.exception(f"schedule_task 执行失败: {e}")
        return {
            "success": False,
            "content": f"操作失败: {str(e)}",
            "images": [],
            "error": str(e),
            "metadata": {}
        }


async def _create_task(
    user_id: int,
    group_id: Optional[int],
    task_description: str,
    minute: str,
    hour: str,
    day: str,
    month: str,
    day_of_week: str,
    silent: Optional[bool],
    one_time: Optional[bool],
    execute_at: str,
    delay_minutes: int,
    mention_user: Optional[bool]
) -> Dict[str, Any]:
    """创建新任务"""
    
    # 检查 silent 参数（必须显式提供）
    if silent is None:
        return {
            "success": False,
            "content": "创建任务时必须提供 silent 参数。请根据任务类型判断：问候/提醒类任务设为 true，搜索/查询类任务设为 false。",
            "images": [],
            "error": "Missing silent parameter",
            "metadata": {}
        }
    
    if not task_description:
        return {
            "success": False,
            "content": "请提供任务描述，说明要执行什么操作",
            "images": [],
            "error": "Missing task_description",
            "metadata": {}
        }
    
    # 判断是否是一次性任务
    is_one_time = one_time if one_time is not None else False
    
    # 判断是否 @ 用户
    should_mention = mention_user if mention_user is not None else False
    
    # 处理一次性任务的时间参数
    execute_datetime = None
    cron_expr = ""
    
    if is_one_time:
        # 一次性任务：优先使用 delay_minutes，其次使用 execute_at
        if delay_minutes > 0:
            from datetime import datetime, timedelta
            execute_datetime = datetime.now() + timedelta(minutes=delay_minutes)
            cron_expr = "一次性任务"
        elif execute_at:
            from datetime import datetime
            try:
                # 尝试解析 ISO8601 格式
                execute_datetime = datetime.fromisoformat(execute_at.replace('Z', '+00:00'))
                cron_expr = "一次性任务"
            except ValueError:
                return {
                    "success": False,
                    "content": f"无效的执行时间格式: {execute_at}。请使用 ISO8601 格式，如 '2024-12-25T08:00:00'",
                    "images": [],
                    "error": "Invalid execute_at format",
                    "metadata": {}
                }
        else:
            return {
                "success": False,
                "content": "一次性任务必须提供 delay_minutes（延迟分钟数）或 execute_at（执行时间）。\n示例：delay_minutes=30 或 execute_at='2024-12-25T08:00:00'",
                "images": [],
                "error": "Missing time parameter for one-time task",
                "metadata": {}
            }
        
        # 检查时间是否已过
        if execute_datetime < datetime.now():
            return {
                "success": False,
                "content": f"执行时间 {execute_datetime.strftime('%Y-%m-%d %H:%M')} 已过，请设置未来的时间",
                "images": [],
                "error": "Execute time in the past",
                "metadata": {}
            }
    else:
        # 循环任务：验证 cron 参数
        if not all([minute, hour, day, month, day_of_week]):
            return {
                "success": False,
                "content": "循环任务必须提供完整的 cron 参数 (minute, hour, day, month, day_of_week)。\n示例：每天8点 → minute='0', hour='8', day='*', month='*', day_of_week='*'\n或设置 one_time=true 创建一次性任务",
                "images": [],
                "error": "Missing cron parameters",
                "metadata": {}
            }
        
        # 构建 cron 表达式
        cron_expr = f"{minute} {hour} {day} {month} {day_of_week}"
        
        # 验证 cron 格式（简单验证）
        parts = cron_expr.split()
        if len(parts) != 5:
            return {
                "success": False,
                "content": f"无效的 cron 表达式: {cron_expr}。需要5个字段: minute hour day month day_of_week",
                "images": [],
                "error": "Invalid cron expression",
                "metadata": {}
            }
    
    # 生成任务摘要
    task_summary = generate_task_summary(task_description)
    
    # 创建任务
    task = scheduler_manager.create_task(
        user_id=user_id,
        group_id=group_id,
        raw_description=task_description,
        task_summary=task_summary,
        cron_expression=cron_expr,
        silent=silent,
        is_one_time=is_one_time,
        execute_at=execute_datetime,
        mention_user=should_mention
    )
    
    # 构建返回消息
    location = f"群{group_id}" if group_id else "私聊"
    
    if is_one_time:
        time_str = execute_datetime.strftime('%Y-%m-%d %H:%M')
        content_lines = [
            f"✅ 一次性任务创建成功！",
            f"",
            f"📋 任务摘要: {task_summary}",
            f"📝 任务描述: {task_description[:80]}{'...' if len(task_description) > 80 else ''}",
            f"⏰ 执行时间: {time_str} (一次性)",
            f"📍 创建位置: {location}",
            f"🔇 静默模式: {'是' if silent else '否'}",
            f"🔔 @提醒: {'是' if should_mention else '否'}",
            f"🆔 任务ID: {task.id}",
            f"",
            f"任务将在指定时间执行一次，执行后自动删除。",
            f"使用「schedule_task list」查看所有任务",
        ]
    else:
        content_lines = [
            f"✅ 定时任务创建成功！",
            f"",
            f"📋 任务摘要: {task_summary}",
            f"📝 任务描述: {task_description[:80]}{'...' if len(task_description) > 80 else ''}",
            f"⏰ 执行时间: {cron_expr}",
            f"📍 创建位置: {location}",
            f"🔇 静默模式: {'是' if silent else '否'}",
            f"🔔 @提醒: {'是' if should_mention else '否'}",
            f"🆔 任务ID: {task.id}",
            f"",
            f"到时间后我会自动执行这个任务，并调用需要的工具来完成。",
            f"使用「schedule_task list」查看所有任务",
        ]
    
    return {
        "success": True,
        "content": "\n".join(content_lines),
        "images": [],
        "error": None,
        "metadata": {
            "task_id": task.id,
            "cron_expression": cron_expr if not is_one_time else None,
            "execute_at": execute_datetime.isoformat() if is_one_time and execute_datetime else None,
            "is_one_time": is_one_time,
            "mention_user": should_mention,
            "task_summary": task_summary
        }
    }


def _list_tasks(user_id: int) -> Dict[str, Any]:
    """列出用户的所有任务"""
    
    tasks = scheduler_manager.get_user_tasks(user_id)
    
    if not tasks:
        return {
            "success": True,
            "content": "您还没有创建定时任务。使用 schedule_task create 来创建。",
            "images": [],
            "error": None,
            "metadata": {"count": 0}
        }
    
    lines = [f"📋 您的定时任务列表（共 {len(tasks)} 个）：\n"]
    
    for i, task in enumerate(tasks, 1):
        status = "🟢" if task.is_active else "⏸️"
        location = f"群{task.group_id}" if task.group_id else "私聊"
        
        # 一次性任务标记
        one_time_mark = " [一次性]" if task.is_one_time else ""
        # @提醒标记
        mention_mark = " [@提醒]" if task.mention_user else ""
        
        lines.append(f"{i}. {status} {task.task_summary}{one_time_mark}{mention_mark}")
        lines.append(f"   ID: {task.id}")
        
        # 显示时间信息
        if task.is_one_time and task.execute_at:
            lines.append(f"   执行时间: {task.execute_at.strftime('%Y-%m-%d %H:%M')} (一次性)")
        else:
            lines.append(f"   时间: {task.cron_expression}")
        
        lines.append(f"   位置: {location}")
        
        if task.execution_count > 0:
            lines.append(f"   已执行: {task.execution_count}次")
        
        if task.last_execution:
            lines.append(f"   上次执行: {task.last_execution.strftime('%m-%d %H:%M')}")
        
        lines.append("")
    
    lines.append("操作命令:")
    lines.append("• schedule_task delete task_id=xxx - 删除任务")
    lines.append("• schedule_task pause task_id=xxx - 暂停任务")
    lines.append("• schedule_task resume task_id=xxx - 恢复任务")
    
    return {
        "success": True,
        "content": "\n".join(lines),
        "images": [],
        "error": None,
        "metadata": {"count": len(tasks), "task_ids": [t.id for t in tasks]}
    }


def _delete_task(user_id: int, task_id: str) -> Dict[str, Any]:
    """删除任务"""
    
    if not task_id:
        return {
            "success": False,
            "content": "请提供任务ID，使用 schedule_task list 查看",
            "images": [],
            "error": "Missing task_id",
            "metadata": {}
        }
    
    success, msg = scheduler_manager.delete_task(task_id, user_id)
    
    if success:
        return {
            "success": True,
            "content": f"✅ {msg}",
            "images": [],
            "error": None,
            "metadata": {"task_id": task_id}
        }
    else:
        return {
            "success": False,
            "content": f"❌ {msg}",
            "images": [],
            "error": msg,
            "metadata": {}
        }


def _pause_task(user_id: int, task_id: str) -> Dict[str, Any]:
    """暂停任务"""
    
    if not task_id:
        return {
            "success": False,
            "content": "请提供任务ID",
            "images": [],
            "error": "Missing task_id",
            "metadata": {}
        }
    
    success, msg = scheduler_manager.pause_task(task_id, user_id)
    
    if success:
        return {
            "success": True,
            "content": f"⏸️ {msg}",
            "images": [],
            "error": None,
            "metadata": {"task_id": task_id}
        }
    else:
        return {
            "success": False,
            "content": f"❌ {msg}",
            "images": [],
            "error": msg,
            "metadata": {}
        }


def _resume_task(user_id: int, task_id: str) -> Dict[str, Any]:
    """恢复任务"""
    
    if not task_id:
        return {
            "success": False,
            "content": "请提供任务ID",
            "images": [],
            "error": "Missing task_id",
            "metadata": {}
        }
    
    success, msg = scheduler_manager.resume_task(task_id, user_id)
    
    if success:
        return {
            "success": True,
            "content": f"▶️ {msg}",
            "images": [],
            "error": None,
            "metadata": {"task_id": task_id}
        }
    else:
        return {
            "success": False,
            "content": f"❌ {msg}",
            "images": [],
            "error": msg,
            "metadata": {}
        }
