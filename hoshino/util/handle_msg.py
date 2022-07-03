from copy import deepcopy
from typing import Union
from nonebot.message import handle_event
from hoshino import Bot, Event, Message, MessageSegment
from hoshino.typing import MessageEvent

async def handle_msg(bot: Bot, event: MessageEvent, msg: Union[Message, str]):
    new_event = deepcopy(event)
    if isinstance(msg, str):
        msg = MessageSegment.text(msg) + ''
    new_event.message = msg
    await handle_event(bot, new_event)
