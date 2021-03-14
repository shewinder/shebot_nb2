from nonebot.message import event_preprocessor
from hoshino import Bot, Event
from hoshino.permission import ADMIN
from hoshino.typing import T_State
from nonebot.adapters.cqhttp import GroupMessageEvent
from loguru import logger
from nonebot.exception import IgnoredException

@event_preprocessor
async def _(bot: Bot, event: Event, state: T_State):
    if isinstance(event, GroupMessageEvent):
        if not await ADMIN(bot, event):
            raise IgnoredException('this event was ignored for GroupMessageEvent is not allowed')
        else:
            logger.info('allowed for admin sender')
    
    
