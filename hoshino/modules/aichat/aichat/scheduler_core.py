"""AI Chat 定时任务核心管理器"""
import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel

from hoshino.schedule import scheduler, add_job
from hoshino import get_bot_list, Message, MessageSegment

from .config import Config
from .api import api_manager
from hoshino import userdata_dir

if TYPE_CHECKING:
    from .session import Session

conf = Config.get_instance('aichat')
aichat_data_dir: Path = userdata_dir.joinpath('aichat')
TASKS_FILE = aichat_data_dir.joinpath('aichat_scheduled_tasks.json')


class ScheduledTask(BaseModel):
    id: str                    # UUID
    user_id: int              # 创建者QQ
    group_id: Optional[int]   # 群组ID（私聊为null）
    raw_description: str      # 用户原始描述（同时作为展示名称）
    cron_expression: str      # cron表达式（循环任务用）
    is_active: bool = True    # 是否激活
    silent: bool = False      # 静默模式：True时不添加任务报告框架
    execution_count: int = 0  # 执行次数
    created_at: datetime      # 创建时间
    updated_at: datetime      # 更新时间
    last_execution: Optional[datetime] = None  # 上次执行时间
    last_result: Optional[str] = None          # 上次执行结果摘要
    # 一次性任务字段
    is_one_time: bool = False                 # 是否为一次性任务
    execute_at: Optional[datetime] = None     # 执行时间（一次性任务用）
    # @ 提醒字段
    mention_user: bool = False                # 执行时是否 @ 任务创建者


class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, ScheduledTask] = {}
        self._job_ids: Dict[str, str] = {}  # task_id -> job_id 映射
    
    def _get_tasks_file(self) -> Path:
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        return TASKS_FILE
    
    def load_tasks(self) -> List[ScheduledTask]:
        file_path = self._get_tasks_file()
        if not file_path.exists():
            logger.info("定时任务文件不存在，创建空任务列表")
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            tasks = []
            for task_data in data.get('tasks', []):
                try:
                    for field in ['created_at', 'updated_at', 'last_execution', 'execute_at']:
                        if task_data.get(field):
                            task_data[field] = datetime.fromisoformat(task_data[field])
                    if 'mention_user' not in task_data:
                        task_data['mention_user'] = False
                    tasks.append(ScheduledTask(**task_data))
                except Exception as e:
                    logger.warning(f"加载任务失败: {e}, 数据: {task_data}")
            
            logger.info(f"已加载 {len(tasks)} 个定时任务")
            return tasks
        except Exception as e:
            logger.exception(f"加载定时任务文件失败: {e}")
            return []
    
    def save_tasks(self):
        file_path = self._get_tasks_file()
        try:
            data = {
                "version": "1.0",
                "updated_at": datetime.now().isoformat(),
                "tasks": []
            }
            
            for task in self.tasks.values():
                task_dict = task.dict()
                for field in ['created_at', 'updated_at', 'last_execution', 'execute_at']:
                    if task_dict.get(field):
                        task_dict[field] = task_dict[field].isoformat()
                data["tasks"].append(task_dict)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"已保存 {len(self.tasks)} 个定时任务")
        except Exception as e:
            logger.exception(f"保存定时任务失败: {e}")
    
    def load_and_schedule(self):
        tasks = self.load_tasks()
        for task in tasks:
            self.tasks[task.id] = task
            if task.is_active:
                self._schedule_task_sync(task)
        
        logger.info(f"定时任务管理器初始化完成，已调度 {len([t for t in tasks if t.is_active])} 个任务")
    
    def _schedule_task_sync(self, task: ScheduledTask):
        try:
            if task.is_one_time and task.execute_at:
                job = add_job(
                    self._execute_task_wrapper,
                    trigger='date',
                    kwargs={'task_id': task.id},
                    run_date=task.execute_at,
                    id=f"aichat_task_{task.id}",
                    replace_existing=True
                )
                self._job_ids[task.id] = job.id
                logger.info(f"已调度一次性任务 {task.id}: {task.execute_at}")
            else:
                job = add_job(
                    self._execute_task_wrapper,
                    trigger='cron',
                    kwargs={'task_id': task.id},
                    id=f"aichat_task_{task.id}",
                    replace_existing=True,
                    **self._cron_to_kwargs(task.cron_expression)
                )
                self._job_ids[task.id] = job.id
                logger.info(f"已调度循环任务 {task.id}: {task.cron_expression}")
        except Exception as e:
            logger.exception(f"调度任务失败 {task.id}: {e}")
    
    def _cron_to_kwargs(self, cron_expr: str) -> Dict[str, Any]:
        parts = cron_expr.split()
        if len(parts) != 5:
            raise ValueError(f"无效的 cron 表达式: {cron_expr}")
        
        return {
            'minute': parts[0],
            'hour': parts[1],
            'day': parts[2],
            'month': parts[3],
            'day_of_week': parts[4],
        }
    
    async def _execute_task_wrapper(self, task_id: str):
        try:
            await self.execute_task(task_id)
        except Exception as e:
            logger.exception(f"执行任务 {task_id} 失败: {e}")
    
    async def execute_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task:
            logger.error(f"任务不存在: {task_id}")
            return
        
        if not task.is_active:
            logger.warning(f"任务 {task_id} 已停用，跳过执行")
            return
        
        logger.info(f"开始执行任务 {task_id}: {task.raw_description[:50]}")
        
        from .session import Session
        from .persona import persona_manager
        
        api_config = api_manager.get_api_config()
        if not api_config:
            logger.error("API 未配置，无法执行任务")
            await self._send_result(task, "任务执行失败：API 未配置")
            return
        
        try:
            # 获取 persona
            persona = persona_manager.get_persona(task.user_id, task.group_id)
            
            # 创建独立 Agent Session，使用唯一 ID 避免与用户 session 冲突
            agent_session_id = f"agent_task_{task.id}_{uuid.uuid4().hex[:6]}"
            temp_session = Session(agent_session_id, persona=persona)
            
            # 明确执行上下文，防止AI误以为是创建定时任务
            temp_session.add_message("system", "【系统提示】你正在执行一个已调度的定时任务。请直接完成下面指定的操作，不要创建新的定时任务，也不要向用户询问确认。")
            temp_session.add_message("user", f"请执行以下任务：{task.raw_description}")
            
            # 调用 chat 执行对话（event=None，复用 session 的环境信息）
            result = await temp_session.chat(api_config)
            
            task.execution_count += 1
            task.last_execution = datetime.now()
            task.last_result = result.content[:500] if result.content else None
            task.updated_at = datetime.now()
            
            if task.is_one_time:
                self.delete_task(task_id, task.user_id)
                logger.info(f"一次性任务 {task_id} 执行完成并已自动删除")
            else:
                self.save_tasks()
            
            content = result.content if result.content else "任务执行完成，但没有返回内容"
            await self._send_result(task, content, temp_session)
            
            if not task.is_one_time:
                logger.info(f"任务 {task_id} 执行完成")
            
        except Exception as e:
            logger.exception(f"任务 {task_id} 执行异常: {e}")
    
    async def _send_result(self, task: ScheduledTask, content: str, session):
        try:
            bots = get_bot_list()
            if not bots:
                logger.warning("没有可用的 Bot，无法发送结果")
                return
            
            bot = bots[0]
            
            logger.debug(f"[Scheduler] 发送任务结果: task_id={task.id}, silent={task.silent}, mention_user={task.mention_user}")
            
            # 构建完整消息（处理图片标识符）
            content_messages = await session.build_message(content)
            
            # 构建任务报告框架
            if task.silent:
                # 静默模式：直接发送内容消息
                final_messages = content_messages
            else:
                # 非静默模式：添加报告框架到第一条消息
                report_text = f"📋 定时任务执行结果\n任务: {task.raw_description[:50]}{'...' if len(task.raw_description) > 50 else ''}\n\n"
                report_msg = MessageSegment.text(report_text)
                
                final_messages = []
                for i, content_msg in enumerate(content_messages):
                    if i == 0:
                        # 第一条消息添加报告框架（使用 + 拼接）
                        final_messages.append(report_msg + content_msg)
                    else:
                        final_messages.append(content_msg)
            
            # 添加 @ 提醒（只在第一条消息添加，使用 + 拼接）
            if task.mention_user and task.group_id and final_messages:
                try:
                    at_prefix = MessageSegment.at(task.user_id) + MessageSegment.text(" ")
                    final_messages[0] = at_prefix + final_messages[0]
                except Exception as e:
                    logger.warning(f"构造 @ 消息失败: {e}")
            
            # 发送所有消息
            if task.group_id:
                for msg in final_messages:
                    await bot.send_group_msg(group_id=task.group_id, message=msg)
            else:
                for msg in final_messages:
                    await bot.send_private_msg(user_id=task.user_id, message=msg)
                
        except Exception as e:
            logger.exception(f"发送任务结果失败: {e}")
    
    def create_task(
        self,
        user_id: int,
        group_id: Optional[int],
        raw_description: str,
        cron_expression: str,
        silent: bool = False,
        is_one_time: bool = False,
        execute_at: Optional[datetime] = None,
        mention_user: bool = False
    ) -> ScheduledTask:
        now = datetime.now()
        task = ScheduledTask(
            id=str(uuid.uuid4())[:8],  # 短ID便于用户使用
            user_id=user_id,
            group_id=group_id,
            raw_description=raw_description,
            cron_expression=cron_expression,
            is_active=True,
            silent=silent,
            execution_count=0,
            created_at=now,
            updated_at=now,
            is_one_time=is_one_time,
            execute_at=execute_at,
            mention_user=mention_user
        )
        
        self.tasks[task.id] = task
        self.save_tasks()
        
        self._schedule_task_sync(task)
        
        return task
    
    def delete_task(self, task_id: str, user_id: int) -> tuple[bool, str]:
        task = self.tasks.get(task_id)
        if not task:
            return False, f"任务 {task_id} 不存在"
        
        if task.user_id != user_id:
            # TODO: 检查是否是超级用户
            return False, "只能删除自己创建的任务"
        
        if task_id in self._job_ids:
            try:
                scheduler.remove_job(self._job_ids[task_id])
            except Exception:
                pass
            del self._job_ids[task_id]
        
        # 删除任务
        del self.tasks[task_id]
        self.save_tasks()
        
        return True, f"已删除任务 {task_id}"
    
    def pause_task(self, task_id: str, user_id: int) -> tuple[bool, str]:
        task = self.tasks.get(task_id)
        if not task:
            return False, f"任务 {task_id} 不存在"
        
        if task.user_id != user_id:
            return False, "只能操作自己创建的任务"
        
        task.is_active = False
        task.updated_at = datetime.now()
        
        if task_id in self._job_ids:
            try:
                scheduler.remove_job(self._job_ids[task_id])
            except Exception:
                pass
        
        self.save_tasks()
        return True, f"已暂停任务 {task_id}"
    
    def resume_task(self, task_id: str, user_id: int) -> tuple[bool, str]:
        task = self.tasks.get(task_id)
        if not task:
            return False, f"任务 {task_id} 不存在"
        
        if task.user_id != user_id:
            return False, "只能操作自己创建的任务"
        
        task.is_active = True
        task.updated_at = datetime.now()
        self.save_tasks()
        
        self._schedule_task_sync(task)
        
        return True, f"已恢复任务 {task_id}"
    
    def get_user_tasks(self, user_id: int) -> List[ScheduledTask]:
        return [t for t in self.tasks.values() if t.user_id == user_id]
    
    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        return self.tasks.get(task_id)


# 全局任务管理器实例
scheduler_manager = TaskManager()


# ============ 模块导入时自动加载并调度所有任务 ============
try:
    scheduler_manager.load_and_schedule()
except Exception as e:
    logger.exception(f"定时任务自动加载失败: {e}")
