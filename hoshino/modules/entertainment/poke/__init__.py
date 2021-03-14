from random import choice
from typing import Callable

from nonebot.adapters.cqhttp import PokeNotifyEvent

from hoshino import Bot, Event, Service, MessageSegment
from hoshino.sres import Res as R
from hoshino.util import DailyNumberLimiter, FreqLimiter
from .config import plugin_config, Config

sv = Service('poke')
conf: Config = plugin_config.config

pkst = sv.on_notice('notify.poke')
_nlt = DailyNumberLimiter(conf.daily_max_num)

_handlers = [] # 处理函数列表

@pkst.handle()
async def _(bot: Bot, event: PokeNotifyEvent):
    if event.target_id != event.self_id:
        return

    uid = event.user_id
    if not _nlt.check(uid):
        await pkst.finish(conf.exceed_notice)

    try:
        handler = choice(_handlers)
        sv.logger.info(f'trying to run {handler.__name__}')
        await handler(bot, event)
    except Exception as e:
        sv.logger.exception(e)

def add_handler():
    def deco(func: Callable) -> Callable:
        _handlers.append(func)
    return deco

@add_handler()
async def send_setu(bot: Bot, event: PokeNotifyEvent):
    pic = R.get_random_img('nr18_setu').cqcode
    await bot.send(event, pic)

@add_handler()
async def poke_back(bot: Bot, event: PokeNotifyEvent):
    uid = event.user_id
    poke = MessageSegment(type='poke',
                          data={'qq': str(uid),})
    await bot.send(event, poke)

@add_handler()
async def send_record(bot: Bot, event: PokeNotifyEvent):
    pic = R.get_random_record('xcw骂')
    await bot.send(event, pic)
    
    


    

    