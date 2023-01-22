import asyncio
import queue
import re

from nonebot.adapters.cqhttp import GroupMessageEvent
from nonebot.adapters.cqhttp.event import MessageEvent, PrivateMessageEvent
from nonebot.typing import T_State
from loguru import logger

from hoshino import Service, Bot, Event, MessageSegment, scheduled_job, sucmd
from hoshino.permission import SUPERUSER
from hoshino.util import DailyNumberLimiter, FreqLimiter
from hoshino.util.handle_msg import handle_msg
from hoshino.sres import Res as R
from .getsetu import *
from .config import Config
from hoshino.config import get_plugin_config_by_name
from hoshino import Message

help_ ="""
[来{1,2,3}份色图] 随机{1,2,3}张色图
[来份xx色图] 发送一张xx关键字色图
[就这不够色] r18色图(需要机器人管理员开启)
""".strip()

conf: Config = get_plugin_config_by_name('setu')

#设置limiter
_num_limiter = DailyNumberLimiter(conf.daily_max_num)
_freq_limiter = FreqLimiter(5)

sv = Service('色图', help_=help_)

common_setu = sv.on_regex(r'^来[份点张](.{1,15})?[涩色瑟]图$', only_group=False)
@common_setu.handle()
async def send_setu(bot: Bot, event: MessageEvent, state: T_State):
    uid = event.user_id

    if not _num_limiter.check(uid):
        await bot.send(event, Message(conf.exceed_notice))
        return

    if not _freq_limiter.check(uid):
        await bot.send(event, Message(conf.too_frequent_notic))
        return

    match: re.Match = state['match']
    num = 1

    #按照数量设置limiter
    _num_limiter.increase(uid, num)
    _freq_limiter.start_cd(uid, num*5)

    keyword = ""
    r18 = False

    if match.group(1):
        keyword: str = match.group(1)
        if keyword.startswith("r18") or keyword.endswith("r18"):
            keyword = keyword.replace("r18", "")
            r18 = True
    
    if r18 and not check_r18(event):
        await bot.send(event, "本群未开启R18")
        return

    logger.info(f"search setu keword: {keyword}, r18: {r18}")
    await bot.send(event, '正在搜索，请稍等~')
    _freq_limiter.start_cd(uid, 10)
    r18_flag = 1 if r18 else 0
    setus = setu_by_keyword(keyword, num, r18=r18_flag)
    
    if not setus:
        await bot.send(event, f'没有找到{keyword}色图')

    async with aiohttp.ClientSession() as session:
        for st in setus:
            await download_setu(session, st)
    await bot.send(event, render_setus(setus))

        
r18_setu = sv.on_command('就这不够色', only_group=False)
@r18_setu.handle()
async def send_r18_setu(bot: Bot, event: MessageEvent, state: T_State):
    await handle_msg(bot, event, f"来点r18色图")

r18_on = sucmd('开启r18')
@r18_on.handle()
async def set_r18(bot: Bot, event: MessageEvent):
    try:
        gid = int(str(event.get_message()))
    except:
        await bot.send(event, f'输入不合法')
        return

    if not gid and isinstance(event, GroupMessageEvent):
        gid = event.group_id

    if gid not in conf.r18_groups:
        conf.r18_groups.append(gid)
        await bot.send(event, f'群{gid}r18开启成功')
    else:
        await bot.send(event, f'群{gid}r18已经开启,无需再次开启')

r18_off = sucmd('关闭r18')
@r18_off.handle()
async def set_r18(bot: Bot, event: MessageEvent):
    try:
        gid = int(str(event.get_message()))
    except:
        await bot.send(event, f'输入不合法')
        return

    if not gid and isinstance(event, GroupMessageEvent):
        gid = event.group_id

    if gid in conf.r18_groups:
        conf.r18_groups.remove(gid)
        await bot.send(event, f'群{gid}r18已关闭')
    else:
        await bot.send(event, f'群{gid}r18已经关闭,无需再次关闭')

def render_setus(setus: List[Setu]) -> Message:
    reply = MessageSegment.text('')
    for setu in setus:
        pic = R.image_from_memory(setu.picbytes)
        reply += MessageSegment.text(f'{setu.title}\n画师：{setu.author}\n画师id：{setu.uid}\npid:{setu.pid}')
        reply += pic
    return reply

def check_r18(event: MessageEvent):
    if isinstance(event, PrivateMessageEvent):
        return True
    if isinstance(event, GroupMessageEvent):
        gid = event.group_id
    else:
        gid = 0
    if gid in conf.r18_groups:
        return True
    else:
        return False
    
 


