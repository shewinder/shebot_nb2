from nonebot.adapters.cqhttp import GroupMessageEvent
from hoshino import Service, Bot, MessageSegment
from hoshino.sres import Res as R
from hoshino.util import DailyNumberLimiter
from .config import plugin_config, Config

conf: Config = plugin_config.config

_nlt = DailyNumberLimiter(conf.daily_max_num)

sv = Service('迫害龙王')
dgk = sv.on_keyword('迫害龙王')

@dgk.handle()
async def tease_dragonking(bot: Bot, event: GroupMessageEvent):
    uid = event.user_id
    if not _nlt.check(uid):
        await dgk.finish(conf.exceed_notice)

    gid = event.group_id
    try:
        talktive = await bot.get_group_honor_info(group_id=gid, type='all')
        dragon_id = talktive['current_talkative']['user_id']
    except:
        await dgk.finish('获取龙王失败')
    if dragon_id == event.self_id:
        antitease_pic = R.get_random_img(folder='antitease').cqcode
        await bot.send(event, antitease_pic)
    else:
        tease_pic = R.get_random_image(folder='龙王')
        await bot.send(event, MessageSegment.at(dragon_id) + tease_pic)

dkg_query = sv.on_command(('查询龙王', '龙王是谁', '谁是龙王'))

@dkg_query.handle()
async def whois_dragonking(bot: Bot, event: GroupMessageEvent):
    gid = event.group_id
    try:
        talktive = await bot.get_group_honor_info(group_id=gid, type='all')
        dragon_id = talktive['current_talkative']['user_id']
        dragon_nickname = talktive['current_talkative']['nickname']
    except:
        await dkg_query.finish('获取龙王失败')
    icon = await R.img_from_url(f'http://q1.qlogo.cn/g?b=qq&nk={dragon_id}&s=160', cache=False)
    ico = icon.cqcode
    reply = f'本群龙王是{dragon_nickname}{icon}'
    await bot.send(event, reply)