import asyncio
import queue

from nonebot.adapters.cqhttp import GroupMessageEvent
from nonebot.adapters.cqhttp.event import MessageEvent, PrivateMessageEvent
from nonebot.typing import T_State
from loguru import logger

from hoshino import Service, Bot, Event, MessageSegment, scheduled_job, sucmd
from hoshino.permission import SUPERUSER
from hoshino.util import DailyNumberLimiter, FreqLimiter
from hoshino.sres import Res as R
from hoshino.glob import R18, NR18
from .getsetu import *
from .config import Config, plugin_config as pc
from hoshino import Message

help_ ="""
[来{1,2,3}份色图] 随机{1,2,3}张色图
[来份xx色图] 发送一张xx关键字色图
[就这不够色] r18色图(需要机器人管理员开启)
""".strip()

conf: Config = pc.config

_num = 10

@scheduled_job('interval', seconds=10)
async def get_lolicon():
    if NR18.qsize() >= _num-2 and R18.qsize() >= _num-2:
        return

    async with aiohttp.ClientSession() as session:
        if NR18.qsize() < _num:
            num = _num - NR18.qsize()
            print('getting lolicon')
            setus = get_lolicon_setu(num=num, r18=0)
            for setu in setus:
                st = await download_setu(session, setu)
                if not st.picbytes:
                    logger.info('image unavailable, skip')
                    continue
                try:
                    NR18.put_nowait(st)
                except queue.Full:
                    print('queue full')
                    pass
        if R18.qsize() < _num:
            print('getting lolicon r18')
            num = 5 - R18.qsize()
            setus = get_lolicon_setu(num=num, r18=1)
            for setu in setus:
                st = await download_setu(session, setu)
                if not st.picbytes:
                    logger.info('image unavailable, skip')
                    continue
                try:
                    R18.put_nowait(st)
                except queue.Full:
                    print('r18 queue full')
                    pass
                


#设置limiter
_num_limiter = DailyNumberLimiter(conf.daily_max_num)
_freq_limiter = FreqLimiter(5)

sv = Service('色图', help_=help_)

common_setu = sv.on_regex(r'^来([1-3])?[份点张](.{1,10})?[涩色瑟]图(.{0,10})$', only_group=False)
@common_setu.handle()
async def send_common_setu(bot: Bot, event: Event, state: T_State):
    uid = event.user_id
    self_id = event.self_id
    gid = None if not isinstance(event, GroupMessageEvent) else event.group_id
    
    if not _num_limiter.check(uid):
        await bot.send(event, conf.exceed_notice)
        return

    if not _freq_limiter.check(uid):
        await bot.send(event, Message(conf.too_frequent_notic))
        return

    match = state['match']
    try:
        num = int(match.group(1))
    except:
        num = 1

    #按照数量设置limiter
    _num_limiter.increase(uid, num)
    _freq_limiter.start_cd(uid, num*5)

    keyword = match.group(2) or match.group(3).strip() 

    if keyword:
        await bot.send(event, '正在搜索，请稍等~')
        _freq_limiter.start_cd(uid, 30) # To relieve net pressure
        logger.info(f'含有关键字{keyword}，尝试搜索')
        r18 = 2 if check_r18(event) else 0 # 开启r18的群搜图混合
        setus = setu_by_keyword(keyword, num, r18=r18)
        if not setus:
            await bot.send(event, f'没有找到{keyword}的色图')
        async with aiohttp.ClientSession() as session:
            for st in setus:
                await download_setu(session, st)
        await bot.send(event, render_setus(setus))

    else:
        setus: List[Setu] = []
        for i in range(num):
            try:
                st = NR18.get_nowait()
                setus.append(st)
            except queue.Empty:
                logger.info('setu empty, waiting for supplying')
    
        if not setus:#send_setus为空
            await bot.send(event,'色图库正在补充，下次再来吧',at_sender=False)
            return

        ret = await bot.send(event, render_setus(setus))
        if gid in conf.delete_groups: # 撤回
            msg_id = ret['message_id']
            self_id = event.self_id
            await asyncio.sleep(conf.delete_after)
            await bot.delete_msg(self_id=self_id, message_id=msg_id)
           
r18_setu = sv.on_command('就这不够色', only_group=False)
@r18_setu.handle()
async def sendR18_setu(bot: Bot, event: MessageEvent, state: T_State):
    self_id = event.self_id
    uid = event.user_id
    if isinstance(event, GroupMessageEvent):
        gid = event.group_id
    else:
        gid = 0

    if not check_r18(event):
        await bot.send(event, '本群未开启r18色图')
        return

    if not _num_limiter.check(uid):
        await bot.send(event, conf.exceed_notice)
        return

    if not _freq_limiter.check(uid):
        await bot.send(event, conf.too_frequent_notic)
        return

    _num_limiter.increase(uid)
    _freq_limiter.start_cd(uid)

    try:
        st: Setu = R18.get_nowait()
    except queue.Empty:
        logger.info('setu empty, waiting for supplying')
        st = None
    if not st:
        await bot.send(event,'色图库正在补充，下次再来吧',at_sender=False)
        return 

    logger.info('发送r18图片')
    pic = R.image_from_memory(st.picbytes)
    reply = MessageSegment.text(f'{st.title}\n画师：{st.author}\npid:{st.pid}') + pic
    ret = await bot.send(event, reply)
    if gid in conf.delete_groups:
        await asyncio.sleep(conf.delete_after)
        await bot.delete_msg(self_id=self_id, message_id=ret['msg_id'])

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
        pc.save_json()
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
        pc.save_json()
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
        return True # 私聊放大权限
    if isinstance(event, GroupMessageEvent):
        gid = event.group_id
    else:
        gid = 0
    if gid in conf.r18_groups:
        return True
    else:
        return False
    
 


