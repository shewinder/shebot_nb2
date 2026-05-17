"""后台任务核心管理器

支持 AI 提交耗时任务到后台执行，任务提交后立即返回，主对话不阻塞。
支持多轮续查（轮询场景），完成后自动通知用户。

任务仅存在于内存中，重启后不恢复。
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel

from ._agent_runner import run_agent
from ._send_util import send_ai_response
from .api import api_manager
from .config import Config
from .persona import persona_manager

if TYPE_CHECKING:
    from .chat_executor import ChatResult

conf = Config.get_instance('aichat')


_BG_SYSTEM_PROMPT = """【后台执行模式】
你正在后台执行用户提交的任务。你的职责是独立完成任务并与用户保持适当距离。

执行规则：
- 直接动手执行，不要问用户任何确认问题
- 如果任务需要等待（下载中、处理中、文件生成中），调用 schedule_continuation 安排后续检查
- 如果任务已完成，直接返回完整结果，不要调用 schedule_continuation
- 不要让用户"稍后再来"——后台任务的价值就是自己持续跟进直到完成
- 不要创建新的定时任务来追踪进度——schedule_continuation 就是为此设计的"""


class BackgroundTask(BaseModel):
    id: str
    user_id: int
    group_id: Optional[int] = None
    task_description: str
    status: str = "pending"  # pending | running | waiting | done | failed | cancelled
    created_at: datetime
    completed_at: Optional[datetime] = None
    result_summary: Optional[str] = None
    error: Optional[str] = None
    continuation_count: int = 0
    max_continuations: int = 10
    next_run_at: Optional[datetime] = None
    context: str = ""


class BackgroundTaskManager:
    def __init__(self):
        self.tasks: Dict[str, BackgroundTask] = {}

    def _count_running(self, user_id: int) -> int:
        count = 0
        for task in self.tasks.values():
            if task.user_id == user_id and task.status in ('pending', 'running', 'waiting'):
                count += 1
        return count

    def get_running_task(self, user_id: int) -> Optional[BackgroundTask]:
        for task in self.tasks.values():
            if task.user_id == user_id and task.status in ('pending', 'running', 'waiting'):
                return task
        return None

    def create_task(
        self,
        user_id: int,
        group_id: Optional[int],
        task_description: str,
    ) -> BackgroundTask:
        running_count = self._count_running(user_id)
        if running_count > 0:
            existing = self.get_running_task(user_id)
            raise RuntimeError(
                f"已有 {running_count} 个后台任务正在执行（ID: {existing.id if existing else 'N/A'}），"
                f"请等待完成后提交新任务"
            )

        task = BackgroundTask(
            id=str(uuid.uuid4())[:8],
            user_id=user_id,
            group_id=group_id,
            task_description=task_description,
            status="pending",
            created_at=datetime.now(),
        )

        self.tasks[task.id] = task
        asyncio.create_task(self._run_task_loop(task))
        logger.info(f"后台任务 {task.id} 已创建: {task_description[:50]}")

        return task

    def cancel_task(self, task_id: str, user_id: int) -> tuple:
        task = self.tasks.get(task_id)
        if not task:
            return False, "任务不存在"
        if task.user_id != user_id:
            return False, "只能取消自己的任务"
        if task.status != "pending":
            return False, f"任务状态为 {task.status}，无法取消（仅 pending 可取消）"

        task.status = "cancelled"
        task.completed_at = datetime.now()
        return True, f"任务 {task_id} 已取消"

    def list_tasks(self, user_id: int) -> List[BackgroundTask]:
        result = []
        for task in self.tasks.values():
            if task.user_id == user_id and task.status != "cancelled":
                result.append(task)
        result.sort(key=lambda t: t.created_at, reverse=True)
        return result

    def _build_continuation_prompt(self, task: BackgroundTask) -> str:
        if not task.context:
            return ""
        return (
            f"\n【上轮进展】\n{task.context}\n\n"
            f"【注意】本轮是第 {task.continuation_count + 1} 次续查，"
            f"最多 {task.max_continuations} 次。"
            f"如果任务已完成，直接返回结果，不要调用 schedule_continuation。"
        )

    def _check_continuation(self, result: "ChatResult") -> Optional[dict]:
        for tr in result.tool_results:
            try:
                parsed = json.loads(tr["result"]["content"])
                if isinstance(parsed, dict):
                    meta = parsed.get("metadata", {})
                    if isinstance(meta, dict) and meta.get("continuation"):
                        return meta
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        return None

    async def _run_task_loop(self, task: BackgroundTask):
        try:
            api_config = api_manager.get_api_config()
            if not api_config or not api_config.get("api_key"):
                task.status = "failed"
                task.error = "API 未配置"
                task.completed_at = datetime.now()
                await self._send_result(task, "任务执行失败：API 未配置", None)
                return

            persona = persona_manager.get_persona(task.user_id, task.group_id)

            while task.continuation_count < task.max_continuations:
                if task.status == "waiting":
                    task.status = "running"
                else:
                    task.status = "running"

                hint = self._build_continuation_prompt(task)
                result = await run_agent(
                    task=f"请执行以下任务：{task.task_description}\n{hint}",
                    system_prompt=_BG_SYSTEM_PROMPT,
                    user_id=task.user_id,
                    group_id=task.group_id,
                    persona=persona,
                    session_prefix=f"bg_task_{task.id}",
                    api_config=api_config,
                )

                cont = self._check_continuation(result)
                if not cont:
                    task.status = "done"
                    task.completed_at = datetime.now()
                    task.result_summary = (result.content or "")[:500]
                    await self._send_result(task, result.content or "任务执行完成，但没有返回内容", None)
                    return

                delay = cont.get("delay_minutes", 5)
                task.status = "waiting"
                task.continuation_count += 1
                task.next_run_at = datetime.now() + timedelta(minutes=delay)
                task.context = cont.get("context", "")

                logger.info(
                    f"后台任务 {task.id} 进入 waiting，"
                    f"第 {task.continuation_count} 次续查，"
                    f"delay={delay}min"
                )
                await asyncio.sleep(delay * 60)

            task.status = "failed"
            task.error = f"达到最大续查次数 ({task.max_continuations})"
            task.completed_at = datetime.now()
            await self._send_result(task, "任务超时：达到最大续查次数，请手动检查状态。", None)

        except Exception as e:
            logger.exception(f"后台任务 {task.id} 执行异常: {e}")
            task.status = "failed"
            task.error = str(e)
            task.completed_at = datetime.now()
            await self._send_result(task, f"任务执行失败: {str(e)}", None)

    async def _send_result(self, task: BackgroundTask, content: str, session):
        try:
            await send_ai_response(
                content, session,
                group_id=task.group_id,
                user_id=task.user_id,
                enable_markdown=conf.enable_markdown_render,
                markdown_min_length=conf.markdown_min_length,
            )

        except Exception as e:
            logger.exception(f"发送后台任务结果失败: {e}")


bg_task_manager = BackgroundTaskManager()
