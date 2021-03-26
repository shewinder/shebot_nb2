import os

from nonebot.adapters.cqhttp import GroupIncreaseNoticeEvent, GroupDecreaseNoticeEvent
from nonebot.adapters.cqhttp.message import MessageSegment
from nonebot.typing import T_State

from hoshino import Service, Bot, Event
from hoshino.util.sutil import load_config, save_config
from hoshino.sres import Res as R

greets_path = os.path.join(os.path.dirname(__file__),'greetings.json')
greetings = load_config(greets_path)
sv = Service('入群欢迎')

set_greet = sv.on_command('设置入群欢迎')
@set_greet.got('greet', prompt='请输入欢迎词')
async def set_greet(bot: "Bot", event: "Event", state: T_State):
    await R.save_image(event)
    greet_word = state['greet']
    global greetings
    gid = event.group_id
    greetings[str(gid)] = greet_word
    save_config(greetings,greets_path)
    await bot.send(event, '设置成功', at_sender=True)
        
greet = sv.on_notice('group_increase')
async def greet(bot: "Bot", event: "GroupIncreaseNoticeEvent"):
    gid = event.group_id
    newer_id = event.user_id
    pic = R.get_random_img('入群欢迎').cqcode
    greet_word = greetings.get(str(gid), MessageSegment.text('欢迎新朋友~收下这份涩图吧')+pic)
    greet_word = MessageSegment.at(newer_id) + greet_word
    await bot.send(event, greet_word)

leave = sv.on_notice('group_decrease')
async def _(bot: "Bot", event: "GroupDecreaseNoticeEvent"):
    id = event.user_id
    await leave.send(f'{id}跑了')

