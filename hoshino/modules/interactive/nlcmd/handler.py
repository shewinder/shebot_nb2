"""
虚拟消息构造与触发处理器
解析LLM返回的命令，构造虚拟消息并触发
"""
from copy import deepcopy
from typing import Dict, Optional
from loguru import logger

from nonebot.adapters.onebot.v11 import MessageSegment, Message
from hoshino import Bot, Event, MessageEvent
from hoshino.util.handle_msg import handle_msg

# 特殊标记，用于避免递归
NLCMD_MARKER = "__NLCMD_INTERNAL__"


def construct_virtual_message(intent: Dict, event: MessageEvent) -> Optional[Message]:
    """
    根据LLM返回的意图构造虚拟消息
    
    Args:
        intent: LLM返回的意图字典，包含command_msg等字段
    
    Returns:
        构造的虚拟消息
    """
    command_msg = intent.get("command_msg", "")
    if not command_msg:
        logger.warning(f"意图中缺少command_msg: {intent}")
        return None
    
    return Message(command_msg)


async def trigger_command(bot: Bot, event: MessageEvent, intent: Dict) -> bool:
    """
    触发命令：构造虚拟消息并调用handle_event
    
    Args:
        bot: Bot实例
        event: 原始事件
        intent: LLM返回的意图字典
    
    Returns:
        是否成功触发
    """
    try:
        # 构造虚拟消息
        virtual_msg = construct_virtual_message(intent, event)
        if not virtual_msg:
            logger.warning("无法构造虚拟消息")
            return False
        
        # 检查是否已经有NLCMD标记（避免递归）
        if hasattr(event, '__dict__') and NLCMD_MARKER in event.__dict__:
            logger.debug("检测到NLCMD标记，跳过处理以避免递归")
            return False
        
        # 在事件上添加标记
        if not hasattr(event, '__dict__'):
            return False
        
        # 使用deepcopy创建新事件，并添加标记
        new_event = deepcopy(event)
        setattr(new_event, NLCMD_MARKER, True)
        
        # 调用handle_msg触发命令
        logger.info(f"触发命令: {virtual_msg}, 置信度: {intent.get('confidence', 0)}")
        await handle_msg(bot, new_event, virtual_msg)
        return True
        
    except Exception as e:
        logger.exception(f"触发命令失败: {e}, 意图: {intent}")
        return False
