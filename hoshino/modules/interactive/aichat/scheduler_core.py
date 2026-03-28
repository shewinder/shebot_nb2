"""
AI Chat 定时任务核心管理器
负责任务的加载、保存、调度和执行
"""
import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel

from hoshino.schedule import scheduler, add_job
from hoshino import get_bot_list, MessageSegment

from .config import Config
from .api import api_manager
from hoshino import userdata_dir

# 加载配置
conf = Config.get_instance('aichat')

# 任务存储文件路径（与 aichat 其他配置放在一起）
aichat_data_dir: Path = userdata_dir.joinpath('aichat')
TASKS_FILE = aichat_data_dir.joinpath('aichat_scheduled_tasks.json')


class ScheduledTask(BaseModel):
    """定时任务数据模型"""
    id: str                    # UUID
    user_id: int              # 创建者QQ
    group_id: Optional[int]   # 群组ID（私聊为null）
    raw_description: str      # 用户原始描述
    task_summary: str         # AI整理后的执行摘要
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
    """定时任务管理器"""
    
    def __init__(self):
        self.tasks: Dict[str, ScheduledTask] = {}
        self._job_ids: Dict[str, str] = {}  # task_id -> job_id 映射
    
    def _get_tasks_file(self) -> Path:
        """获取任务文件路径"""
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        return TASKS_FILE
    
    def load_tasks(self) -> List[ScheduledTask]:
        """从 JSON 文件加载任务"""
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
                    # 处理 datetime 字符串
                    for field in ['created_at', 'updated_at', 'last_execution', 'execute_at']:
                        if task_data.get(field):
                            task_data[field] = datetime.fromisoformat(task_data[field])
                    # 向后兼容：如果 mention_user 不存在，默认为 False
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
        """保存任务到 JSON 文件"""
        file_path = self._get_tasks_file()
        try:
            data = {
                "version": "1.0",
                "updated_at": datetime.now().isoformat(),
                "tasks": []
            }
            
            for task in self.tasks.values():
                task_dict = task.dict()
                # 处理 datetime 对象
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
        """启动时加载并调度所有激活的任务（同步方式，模块导入时调用）"""
        tasks = self.load_tasks()
        for task in tasks:
            self.tasks[task.id] = task
            if task.is_active:
                self._schedule_task_sync(task)
        
        logger.info(f"定时任务管理器初始化完成，已调度 {len([t for t in tasks if t.is_active])} 个任务")
    
    def _schedule_task_sync(self, task: ScheduledTask):
        """将任务添加到 APScheduler（同步版本）"""
        try:
            if task.is_one_time and task.execute_at:
                # 一次性任务使用 date trigger
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
                # 循环任务使用 cron trigger
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
        """将 cron 表达式转换为 APScheduler kwargs"""
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
        """任务执行包装器（处理异常）"""
        try:
            await self.execute_task(task_id)
        except Exception as e:
            logger.exception(f"执行任务 {task_id} 失败: {e}")
    
    async def execute_task(self, task_id: str):
        """执行指定任务"""
        task = self.tasks.get(task_id)
        if not task:
            logger.error(f"任务不存在: {task_id}")
            return
        
        if not task.is_active:
            logger.warning(f"任务 {task_id} 已停用，跳过执行")
            return
        
        logger.info(f"开始执行任务 {task_id}: {task.task_summary}")
        
        # 动态导入避免循环依赖
        from .chat import call_ai_api_with_tools
        from .tools import get_available_tools
        from .persona import persona_manager
        
        # 获取任务创建者的当前人格
        persona = persona_manager.get_persona(task.user_id, task.group_id)
        
        # 构建 system content
        if persona:
            system_content = f"{persona}\n\n你正在执行一个定时任务。请根据用户的任务描述执行操作，"
            system_content += "你可以调用任何可用工具来完成任务。请尽可能详细地完成任务，并在完成后总结执行结果。"
        else:
            system_content = "你是一个任务执行助手。请根据用户的任务描述执行操作。\n"
            system_content += "你可以调用任何可用工具来完成任务。请尽可能详细地完成任务，并在完成后总结执行结果。"
        
        # 构建执行消息
        messages = [
            {
                "role": "system",
                "content": system_content
            },
            {
                "role": "user",
                "content": task.raw_description
            }
        ]
        
        # 获取 API 配置
        api_config = api_manager.get_api_config()
        if not api_config:
            logger.error("API 未配置，无法执行任务")
            await self._send_result(task, "任务执行失败：API 未配置")
            return
        
        # 调用 AI 执行任务
        try:
            result = await call_ai_api_with_tools(
                messages=messages,
                api_config=api_config,
                max_tool_rounds=10,
                context={"scheduled_task": task}
            )
            
            # 更新任务状态
            task.execution_count += 1
            task.last_execution = datetime.now()
            task.last_result = result.get("content", "")[:500] if result.get("content") else None
            task.updated_at = datetime.now()
            
            # 一次性任务执行后自动删除
            if task.is_one_time:
                self.delete_task(task_id, task.user_id)
                logger.info(f"一次性任务 {task_id} 执行完成并已自动删除")
            else:
                self.save_tasks()
            
            # 发送结果
            content = result.get("content", "任务执行完成，但没有返回内容")
            await self._send_result(task, content)
            
            if not task.is_one_time:
                logger.info(f"任务 {task_id} 执行完成")
            
        except Exception as e:
            logger.exception(f"任务 {task_id} 执行异常: {e}")
            await self._send_result(task, f"任务执行异常: {str(e)[:200]}")
    
    async def _send_result(self, task: ScheduledTask, content: str):
        """发送执行结果给用户"""
        try:
            # 延迟导入避免循环导入问题
            bots = get_bot_list()
            if not bots:
                logger.warning("没有可用的 Bot，无法发送结果")
                return
            
            bot = bots[0]
            
            # 根据 silent 标记决定是否添加报告框架
            if task.silent:
                # 静默模式：直接发送内容（适合问候、提醒类任务）
                message = content[:1000]
            else:
                # 正常模式：添加任务报告框架
                msg_lines = [
                    "📋 定时任务执行结果",
                    f"任务: {task.task_summary[:50]}{'...' if len(task.task_summary) > 50 else ''}",
                    "",
                    f"{content[:800]}{'...' if len(content) > 800 else ''}"
                ]
                message = "\n".join(msg_lines)
            
            # 如果需要 @ 用户，在消息开头添加 at（仅在群聊中有效）
            if task.mention_user and task.group_id:
                try:
                    message = MessageSegment.at(task.user_id) + " " + message
                except Exception as e:
                    logger.warning(f"构造 @ 消息失败: {e}")
            
            if task.group_id:
                # 群聊场景：发送到群
                await bot.send_group_msg(group_id=task.group_id, message=message)
            else:
                # 私聊场景：私聊反馈
                await bot.send_private_msg(user_id=task.user_id, message=message)
                
        except Exception as e:
            logger.exception(f"发送任务结果失败: {e}")
    
    def create_task(
        self,
        user_id: int,
        group_id: Optional[int],
        raw_description: str,
        task_summary: str,
        cron_expression: str,
        silent: bool = False,
        is_one_time: bool = False,
        execute_at: Optional[datetime] = None,
        mention_user: bool = False
    ) -> ScheduledTask:
        """创建新任务"""
        now = datetime.now()
        task = ScheduledTask(
            id=str(uuid.uuid4())[:8],  # 短ID便于用户使用
            user_id=user_id,
            group_id=group_id,
            raw_description=raw_description,
            task_summary=task_summary,
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
        
        # 立即调度（同步方式）
        self._schedule_task_sync(task)
        
        return task
    
    def delete_task(self, task_id: str, user_id: int) -> tuple[bool, str]:
        """删除任务"""
        task = self.tasks.get(task_id)
        if not task:
            return False, f"任务 {task_id} 不存在"
        
        # 检查权限（只能删除自己的任务，超管除外）
        if task.user_id != user_id:
            # TODO: 检查是否是超级用户
            return False, "只能删除自己创建的任务"
        
        # 移除调度
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
        """暂停任务"""
        task = self.tasks.get(task_id)
        if not task:
            return False, f"任务 {task_id} 不存在"
        
        if task.user_id != user_id:
            return False, "只能操作自己创建的任务"
        
        task.is_active = False
        task.updated_at = datetime.now()
        
        # 移除调度
        if task_id in self._job_ids:
            try:
                scheduler.remove_job(self._job_ids[task_id])
            except Exception:
                pass
        
        self.save_tasks()
        return True, f"已暂停任务 {task_id}"
    
    def resume_task(self, task_id: str, user_id: int) -> tuple[bool, str]:
        """恢复任务"""
        task = self.tasks.get(task_id)
        if not task:
            return False, f"任务 {task_id} 不存在"
        
        if task.user_id != user_id:
            return False, "只能操作自己创建的任务"
        
        task.is_active = True
        task.updated_at = datetime.now()
        self.save_tasks()
        
        # 重新调度（同步方式）
        self._schedule_task_sync(task)
        
        return True, f"已恢复任务 {task_id}"
    
    def get_user_tasks(self, user_id: int) -> List[ScheduledTask]:
        """获取用户的所有任务"""
        return [t for t in self.tasks.values() if t.user_id == user_id]
    
    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """获取单个任务"""
        return self.tasks.get(task_id)


# 全局任务管理器实例
scheduler_manager = TaskManager()


def generate_task_summary(description: str) -> str:
    """
    生成任务摘要（直接截取前20字）
    """
    if not description:
        return "未命名任务"
    
    # 截取前20字，超长时添加省略号
    if len(description) <= 20:
        return description
    return description[:20] + "..."


# ============ 模块导入时自动加载并调度所有任务 ============
try:
    scheduler_manager.load_and_schedule()
except Exception as e:
    logger.exception(f"定时任务自动加载失败: {e}")
