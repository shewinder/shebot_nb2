"""后台任务工具

为 AI 提供 run_background_task 和 schedule_continuation 两个工具。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

from ..registry import tool_registry, ok, fail
from ...background_task_core import bg_task_manager

if TYPE_CHECKING:
    from hoshino import Event
    from ...session import Session


def _format_task_list(tasks: list) -> str:
    if not tasks:
        return "您还没有后台任务。使用时说「帮我后台执行...」即可提交。\n提交后可以使用 action=list 查看进度。"

    lines = [f"📋 后台任务列表（共 {len(tasks)} 个）：\n"]

    status_emoji = {
        "pending": "⏳",
        "running": "🔄",
        "waiting": "⏸️",
        "done": "✅",
        "failed": "❌",
    }

    for i, task in enumerate(tasks, 1):
        emoji = status_emoji.get(task.status, "❓")
        location = f"群{task.group_id}" if task.group_id else "私聊"

        desc = task.task_description[:30]
        if len(task.task_description) > 30:
            desc += "..."

        lines.append(f"{i}. {emoji} {desc}")
        lines.append(f"   ID: {task.id} | 状态: {task.status}")

        if task.status == "waiting" and task.next_run_at:
            remaining = task.next_run_at - datetime.now()
            minutes = max(0, int(remaining.total_seconds() / 60))
            lines.append(f"   预计 {minutes} 分钟后继续（第 {task.continuation_count}/{task.max_continuations} 轮）")
        elif task.status in ("running", "pending"):
            pass
        else:
            lines.append(f"   完成时间: {task.completed_at.strftime('%m-%d %H:%M') if task.completed_at else 'N/A'}")

        if task.result_summary:
            summary = task.result_summary[:40] + "..." if len(task.result_summary) > 40 else task.result_summary
            lines.append(f"   结果: {summary}")

        lines.append("")

    lines.append("操作命令:")
    lines.append("• run_background_task action=cancel task_id=xxx - 取消 pending 状态的任务")

    return "\n".join(lines)


@tool_registry.register(
    name="run_background_task",
    description="""启动、查看或取消后台任务。

## ⚠️ 何时必须使用本工具（重要）
遇到以下耗时操作时，必须使用 action=start 提交后台任务，而不是在当前对话中直接调用其他工具：
- 任何下载操作（磁力链接、BT种子、PT站资源、大文件）——下载是耗时操作，必须后台
- 需要轮询等待外部服务完成的操作（如下载后检查进度、等待处理结果）
- 预计耗时超过 30 秒的任何多步骤操作
- 操作包含"先做X，等待，再做Y"这种等待链

如果你不确定是否耗时，优先使用本工具。提交后直接告诉用户"已开始后台执行，完成后通知你"即可。

## 操作说明
- start: 提交新任务。AI 会在后台独立完成任务链（包括定时检查进度），完成后自动通知用户。
- list: 查看当前用户的所有后台任务及进度。
- cancel: 取消一个 pending 状态的任务（已开始执行的任务无法取消）。

## start 时 task_description 填写规范
task_description 应该详细描述完整的任务链，包括所有步骤。AI 在后台可以调用 schedule_continuation 定时检查进度。
示例:
- "监控 qBittorrent 中xx电影的下载进度，下载完成后汇报文件信息（文件名、大小、路径）"
- "监控 qBittorrent 中「Oppenheimer.2023.1080p」的下载进度，完成后汇报"
- "搜索今日AI新闻，生成一份简报发送给用户"
- "分析用户最近的聊天记录，总结关注点"

注意：添加下载任务是秒级操作，应在当前对话中内联完成。只有监控下载进度这种需要等待的操作才用本工具。"

## 限制
- 每用户同时只能有 1 个运行中的后台任务
- 任务创建后可通过 list 查看进度""",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型: start/list/cancel",
                "enum": ["start", "list", "cancel"]
            },
            "task_description": {
                "type": "string",
                "description": "任务描述，详细说明要执行的操作。start 时必需。"
            },
            "task_id": {
                "type": "string",
                "description": "任务ID，cancel 时必需。从 list 结果中获取。"
            },
            "preactivate_skills": {
                "type": "array",
                "items": {"type": "string"},
                "description": "预激活的 SKILL 名称列表。传入 sub agent 执行任务需要用到的 SKILL，避免首轮再调 activate_skill。"
            }
        },
        "required": ["action"]
    }
)
async def run_background_task(
    action: str,
    task_description: str = "",
    task_id: str = "",
    preactivate_skills: Optional[List[str]] = None,
    session: Optional["Session"] = None,
    event: Optional["Event"] = None,
) -> Dict[str, Any]:
    action = action.lower().strip()

    # 获取用户信息
    user_id = None
    group_id = None

    if event:
        user_id = event.user_id
        group_id = getattr(event, 'group_id', None)

    if not user_id and session:
        sid = getattr(session, 'session_id', '')
        if 'user_' in sid:
            try:
                user_id = int(sid.split('user_')[-1].split('_')[0])
            except (ValueError, IndexError):
                pass

    if not user_id:
        return fail("无法获取用户信息", error="Missing user context")

    try:
        if action == "start":
            if not task_description:
                return fail("请提供任务描述，说明要后台执行什么操作")

            try:
                task = bg_task_manager.create_task(user_id, group_id, task_description, preactivate_skills)
            except RuntimeError as e:
                existing = bg_task_manager.get_running_task(user_id)
                status_text = f"状态: {existing.status}" if existing else ""
                return fail(
                    f"您已有一个后台任务正在执行，请等待完成后提交新任务。\n"
                    f"当前任务 ID: {existing.id if existing else 'N/A'} {status_text}\n"
                    f"使用 action=list 查看详情。",
                    metadata={"active_task_id": existing.id if existing else None}
                )

            return ok(
                f"后台任务已提交！\n\n"
                f"📝 任务: {task_description[:80]}{'...' if len(task_description) > 80 else ''}\n"
                f"🆔 任务ID: {task.id}\n"
                f"⏳ 状态: 等待执行\n\n"
                f"任务将在后台独立执行，完成后通知您。\n"
                f"使用 action=list 查看进度。",
                metadata={"task_id": task.id}
            )

        elif action == "list":
            tasks = bg_task_manager.list_tasks(user_id)
            return ok(
                _format_task_list(tasks),
                metadata={"count": len(tasks), "task_ids": [t.id for t in tasks]}
            )

        elif action == "cancel":
            if not task_id:
                return fail("请提供要取消的任务ID（从 action=list 获取）")

            success, msg = bg_task_manager.cancel_task(task_id, user_id)
            if success:
                return ok(f"✅ {msg}", metadata={"task_id": task_id})
            return fail(f"❌ {msg}", error=msg)

        else:
            return fail(f"未知操作: {action}。支持: start/list/cancel")

    except Exception as e:
        logger.exception(f"run_background_task 执行失败: {e}")
        return fail(f"操作失败: {str(e)}", error=str(e))


@tool_registry.register(
    name="schedule_continuation",
    description="""【后台任务专用】暂停当前执行并安排后续检查。

## 使用场景
- 提交了一个需要时间完成的操作（下载、转码、文件生成），需要定时检查进度
- 多步骤任务中需要等待上一步的结果

## delay_minutes 设置指南
- 检查下载进度：1-3 分钟
- 等待文件处理完成：5-10 分钟
- 图像生成任务：1-2 分钟

## context 填写指南
记录本轮关键进展和下一轮需要做什么，格式自由。下一轮执行时会作为【上轮进展】注入。
建议包含：已完成哪些步骤、当前进度、下一步要检查什么。

调用此工具后，任务会在指定时间后自动恢复，继续执行。""",
    parameters={
        "type": "object",
        "properties": {
            "delay_minutes": {
                "type": "integer",
                "description": "多少分钟后继续执行（1-60）",
                "minimum": 1,
                "maximum": 60
            },
            "why": {
                "type": "string",
                "description": "为什么需要等待（简要说明当前状态）"
            },
            "context": {
                "type": "string",
                "description": "本轮进展和下一轮要做什么，下一轮作为上下文注入"
            }
        },
        "required": ["delay_minutes", "why"]
    }
)
async def schedule_continuation(
    delay_minutes: int,
    why: str,
    context: str = "",
) -> Dict[str, Any]:
    delay_minutes = max(1, min(delay_minutes, 60))

    return ok(
        f"已安排 {delay_minutes} 分钟后继续: {why}",
        metadata={
            "continuation": True,
            "delay_minutes": delay_minutes,
            "why": why,
            "context": context,
        }
    )
