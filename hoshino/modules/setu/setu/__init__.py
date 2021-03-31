import asyncio
import threading
from os import path

from nonebot.adapters.cqhttp import GroupMessageEvent
from nonebot.typing import T_State
from loguru import logger

from hoshino import Service, Bot, Event, MessageSegment
from hoshino.permission import SUPERUSER
from hoshino.util import DailyNumberLimiter, FreqLimiter
from hoshino.util.sutil import download_async
from hoshino.sres import Res as R
from .getsetu import *
from .config import Config, plugin_config as pc
from .data_source import load_config, save_config, SetuWarehouse, send_setus

conf: Config = pc.config

#初始化色图仓库
nr18_path = path.join(R.image_dir, 'nr18_setu') #存放非r18图片
r18_path = path.join(R.image_dir, 'r18_setu') #存放r18图片
search_path = path.join(R.image_dir, 'search_setu') #存放搜索图片
if not os.path.exists(search_path):
    os.mkdir(search_path)
wh = SetuWarehouse(nr18_path)
r18_wh = SetuWarehouse(r18_path, r18=1)

#启动一个线程一直补充色图
thd = threading.Thread(target=wh.keep_supply)
if conf.online_mode:
    print('线程启动')
    thd.start()

#启动一个线程一直补充r18色图
thd_r18 = threading.Thread(target=r18_wh.keep_supply)
if conf.online_mode:
    print('r18线程启动')
    thd_r18.start()

#设置limiter
_num_limiter = DailyNumberLimiter(conf.daily_max_num)
_freq_limiter = FreqLimiter(5)

sv = Service('色图')

common_setu = sv.on_regex(r'^来?([1-3])?[份点张]?(.{1,10})?[涩色瑟]图(.{0,10})$', only_group=False)
@common_setu.handle()
async def send_common_setu(bot, event: Event, state: T_State):
    uid = event.user_id
    self_id = event.self_id
    gid = None if not isinstance(event, GroupMessageEvent) else event.group_id
    
    is_to_delete = True if gid in conf.delete_groups else False

    if not _num_limiter.check(uid):
        await bot.send(event, conf.exceed_notice)
        return

    if not _freq_limiter.check(uid):
        await bot.send(event, conf.too_frequent_notic)
        return

    match = state['match']
    try:
        num = int(match.group(1))
    except:
        num = 1

    #按照数量设置limiter
    _num_limiter.increase(uid,num)
    _freq_limiter.start_cd(uid,num*5)

    keyword = match.group(2) or match.group(3).strip() 

    if not conf.online_mode and not keyword:
        logger.info('发送本地涩图')
        _num_limiter.increase(uid)
        pic = R.get_random_img('nr18_setu').cqcode
        ret = await bot.send(event,  pic)
        msg_id = ret['message_id']
        if is_to_delete:
            #30秒后删除
            await asyncio.sleep(conf.delete_after)
            await bot.delete_msg(self_id=self_id, message_id=msg_id)
        return
    if keyword:
        await bot.send(event, '正在搜索，请稍等~')
        _freq_limiter.start_cd(uid, 30) # To relieve net pressure
        logger.info(f'含有关键字{keyword}，尝试搜索')

        if conf.search_strategy == 0: # 优先api
            if await SUPERUSER(bot, event): # SUPERUSER 搜图可以搜出r18, 给自己用
                setus = get_setu(r18=2, keyword=keyword, num=2) or search_in_database(keyword, 2, 2)
            else:
                setus = get_setu(r18=0, keyword=keyword, num=1) or search_in_database(keyword, 1, 0)
        elif conf.search_strategy == 1:
            if await SUPERUSER(bot, event): # SUPERUSER 搜图可以搜出r18, 给自己用
                setus = search_in_database(keyword, 2, 2) or get_setu(r18=2, keyword=keyword, num=2)
            else:
                setus = search_in_database(keyword, 1, 0) or get_setu(r18=0, keyword=keyword, num=1)          

            if not setus:
                await bot.send(event, f'没有找到关键字{keyword}的涩图')
                logger.info(f'{uid} searched keyword {keyword} and returned no result')
                return

        for setu in setus:
            pic_path = await download_async(setu.url, search_path, str(setu.pid))
            pic = R.image(pic_path)
            reply = MessageSegment.text(f'{setu.title}\n画师：{setu.author}\npid:{setu.pid}')
            reply += pic
            try:
                await bot.send(event,reply,at_sender=False)
            except Exception as ex:
                await bot.send(event, f'搜索关键字{keyword}发生异常')
                logger.error(f'搜索涩图时发生异常 {ex}')
    else:
        setus = wh.fetch(num)
        if not setus:#send_setus为空
            await bot.send(event,'色图库正在补充，下次再来吧',at_sender=False)
            return
        else:
            await send_setus(bot,event,'nr18_setu', setus, conf.with_url, is_to_delete)            

r18_setu = sv.on_command('就这不够色', only_group=False)
@r18_setu.handle()
async def send_r18_setu(bot: Bot, event: Event, state: T_State):
    uid = event.get_user_id
    if not isinstance(event, GroupMessageEvent):
        gid = None
    gid = event.group_id
    is_to_delete = True if gid in conf.delete_groups else False
    self_id = event.self_id

    if gid not in conf.r18_groups and gid!= 0:
        await bot.send(event,'本群未开启r18色图')
        return

    if not _num_limiter.check(uid):
        await bot.send(event, conf.exceed_notice)
        return

    if not _freq_limiter.check(uid):
        await bot.send(event, conf.too_frequent_notic)
        return

    if not conf.online_mode:
        _num_limiter.increase(uid)
        logger.info('发送本地r18涩图')
        pic = R.get_random_image('r18_setu')
        ret = await bot.send(event,pic)

        msg_id = ret['message_id']
        if is_to_delete:
            await asyncio.sleep(conf.delete_after)
            await bot.delete_msg(self_id=self_id, message_id=msg_id)
        return   

    _num_limiter.increase(uid)
    _freq_limiter.start_cd(uid)

    setus = r18_wh.fetch(1)
    logger.info('发送r18图片')
    await send_setus(bot, event, 'r18_setu', setus, conf.with_url, is_to_delete)


