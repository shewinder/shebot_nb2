from copy import deepcopy
from typing import Union
from nonebot.message import handle_event
from hoshino import Bot, Event, Message, MessageSegment
from hoshino.event import MessageEvent
from hoshino.log import logger

async def handle_msg(bot: Bot, event: MessageEvent, msg: Union[Message, str]):
    logger.info(f"[handle_msg] 开始处理: user_id={getattr(event, 'user_id', '?')}, group_id={getattr(event, 'group_id', '?')}")
    if isinstance(msg, str):
        logger.info(f"[handle_msg] 文本消息: {msg[:100]}")
    else:
        seg_types = [seg.type for seg in msg]
        logger.info(f"[handle_msg] 消息段类型: {seg_types}")
    
    new_event = deepcopy(event)
    if isinstance(msg, str):
        msg = MessageSegment.text(msg) + ''
    new_event.message = msg
    # handle_event处理时at信息一已经被剥掉，所以传参的msg不添加at
    logger.info("[handle_msg] 调用 handle_event")
    try:
        await handle_event(bot, new_event)
        logger.info("[handle_msg] handle_event 完成")
    except Exception as e:
        logger.exception(f"[handle_msg] handle_event 异常: {e}")
