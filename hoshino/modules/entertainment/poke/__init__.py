from random import choice
from typing import Callable

from nonebot.adapters.cqhttp import PokeNotifyEvent

from hoshino import Bot, Service, MessageSegment
from hoshino.glob import NR18
from hoshino.sres import Res as R

sv = Service('poke')

pkst = sv.on_notice('notify.poke')

_handlers = [] # 处理函数列表

@pkst.handle()
async def _(bot: Bot, event: PokeNotifyEvent):
    if event.target_id != event.self_id:
        return

    uid = event.user_id

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
    st = NR18.get_nowait()
    await bot.send(event, R.image_from_memory(st.picbytes))

@add_handler()
async def poke_back(bot: Bot, event: PokeNotifyEvent):
    uid = event.user_id
    poke = MessageSegment(type='poke',
                          data={'qq': str(uid),})
    await bot.send(event, poke)

@add_handler()
async def send_record(bot: Bot, event: PokeNotifyEvent):
    pic = R.get_random_record('record/xcw骂')
    await bot.send(event, pic)
    
    


    

    