from typing import Dict
from loguru import logger
from hoshino import Service, Bot, Event, Message
import random
from hoshino.sres import Res as R
sv = Service('chat', visible=False)


async def nihaole(bot: Bot, event: Event):
    await bot.send(event, '不许好,憋回去！')
sv.on_command('我好了').handle()(nihaole)


async def ddhaole(bot: Bot, event: Event):
    await bot.send(event, '那个朋友是不是你弟弟？')
sv.on_command('我有个朋友说他好了', aliases=('我朋友说他好了', )).handle()(ddhaole)

async def laopo(bot: Bot, event: Event):
    await bot.send(event, '这位先生，你没有老婆')
sv.on_keyword(keywords=['老婆'], only_to_me=True).handle()(laopo)

sv1 = Service('repeat', visible=False)


class repeater:
    def __init__(self, msg: str , repeated: bool , prob: float) -> None:
        self.msg = msg
        self.repeated = repeated
        self.prob = prob

    def check(self, current_msg: str) -> bool:
        return not self.repeated and current_msg == self.msg


# 想了想要复现HoshinoBot的复读还是得有个全局字典来存数据F
GROUP_STATE: Dict[int, repeater] = dict()


async def random_repeat(bot: Bot, event: Event):
    gid = event.group_id
    msg = event.raw_message
    if gid not in GROUP_STATE:
        GROUP_STATE[gid] =  repeater(msg, False, 0.0)
        return
    current_repeater = GROUP_STATE[gid]
    if current_repeater.check(msg):
        if  p :=current_repeater.prob > random.random():
            try:
                GROUP_STATE[gid] =  repeater(msg, True, 0.0)
                await bot.send(event,Message(msg))
            except Exception as e:
                logger.exception(e)
        else:
            p = 1-(1-p) / 1.6
            GROUP_STATE[gid] =  repeater(msg, False, p)
    else:
        GROUP_STATE[gid] =  repeater(msg, False, 0.0)
# 优先级为0，为了避免被正常命令裁剪message
sv1.on_message(priority=0,block=False).handle()(random_repeat)