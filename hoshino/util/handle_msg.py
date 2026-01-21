from copy import deepcopy
from typing import Union
from nonebot.message import handle_event
from hoshino import Bot, Event, Message, MessageSegment
from hoshino.event import MessageEvent

async def handle_msg(bot: Bot, event: MessageEvent, msg: Union[Message, str]):
    new_event = deepcopy(event)
    if isinstance(msg, str):
        msg = MessageSegment.text(msg) + ''
    new_event.message = msg
    # handle_event处理时at信息一已经被剥掉，所以传参的msg不添加at
    await handle_event(bot, new_event)
