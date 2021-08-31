import asyncio
import datetime

from nonebot.adapters.cqhttp.message import Message, MessageSegment
from hoshino.rule import keyword

from hoshino import Service, Bot, Event, scheduled_job, get_bot_list
from hoshino.sres import Res as R

from .data_source import get_rank
from hoshino.util.sutil import get_send_groups
from hoshino.log import logger

sv = Service('Pixiv日榜', enable_on_default=False)
keyword = [
    '原神', 
    'genshin', 
    'yuri', 
    'loli', 
    'lolicon', 
    '萝莉', 
    '百合', 
    '公主连接',
    'pcr', 
    '公主链接']

@scheduled_job('cron', hour=18, minute=30, id='pixiv日榜')
async def pixiv_rank():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    date = f'{yesterday}'
    urls = await get_rank(date, num=500, keyword=keyword)
    if len(urls) > 15:
        urls = urls[0:15]
    bot: Bot = get_bot_list()[0]
    gids = await get_send_groups(sv_name=sv.name)
    count = 0
    for gid in gids:
        await asyncio.sleep(0.5)
        try:
            imgs = [MessageSegment.image(url) for url in urls]
            print(imgs)
            await bot.send_group_msg(message=Message(imgs), group_id=gid)
            count += 1
            logger.info(f"群{gid} 投递成功！")
        except Exception as e:
            logger.exception(e)
            logger.error(type(e))