import asyncio
import datetime

from nonebot.adapters.cqhttp.event import Event
from nonebot.typing import T_State

from hoshino import Service, Bot
from nonebot.adapters.cqhttp.message import Message, MessageSegment

from hoshino.sres import Res as R

sv = Service('原神伤害计算')

add_chara = sv.on_command('add chara', aliases={'添加角色'})

supported = ['胡桃', '甘雨', '宵宫']

@add_chara.handle()
def add_character(bot: Bot, event: Event, state: T_State):
    msg = str(event.get_message()).strip()
    if msg:
        state['name'] = msg

@add_chara.got('name', prompt='请输入角色名, 目前支持{su}')
