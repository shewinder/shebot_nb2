from hoshino import Service, Bot, MessageSegment, res_dir
from hoshino.event import GroupMessageEvent, HonorNotifyEvent
from hoshino.sres import Res as R
from hoshino.util import DailyNumberLimiter
from hoshino.util.sutil import get_img_from_url
from .config import Config

help_ = '[迫害龙王] 艾特龙王出来并迫害'

plug_res = res_dir.joinpath('teasedragonking')

conf = Config.get_instance('teasedragonking')

_nlt = DailyNumberLimiter(conf.daily_max_num)

_dgk = {} # 保存龙王数据

sv = Service('迫害龙王', help_=help_)
dgk = sv.on_keyword('迫害龙王')

@dgk.handle()
async def tease_dragonking(bot: Bot, event: GroupMessageEvent):
    uid = event.user_id
    if not _nlt.check(uid):
        await dgk.finish(conf.exceed_notice)

    gid = event.group_id
    dragon_id = _dgk.get(gid)
    if not dragon_id:
        try:
            talktive = await bot.get_group_honor_info(group_id=gid, type='all')
            dragon_id = talktive['current_talkative']['user_id']
        except IndexError:
            await dgk.finish('获取龙王失败')
    if dragon_id == event.self_id:
        antitease_pic = R.get_random_img(folder='teasedragonking/antitease').cqcode
        await bot.send(event, antitease_pic)
    else:
        tease_pic = R.get_random_img(folder='teasedragonking/龙王').cqcode
        await bot.send(event, MessageSegment.at(dragon_id) + tease_pic)

dkg_query = sv.on_command(('查询龙王', '龙王是谁', '谁是龙王'))

@dkg_query.handle()
async def whois_dragonking(bot: Bot, event: GroupMessageEvent):
    gid = event.group_id
    talktive = _dgk.get(gid)
    if not talktive:
        try:
            talktive = await bot.get_group_honor_info(group_id=gid, type='all')
            dragon_id = talktive['current_talkative']['user_id']
            dragon_nickname = talktive['current_talkative']['nickname']
        except IndexError:
            await dkg_query.finish('获取龙王失败')
    icon = await get_img_from_url(f'http://q1.qlogo.cn/g?b=qq&nk={dragon_id}&s=160')
    icon = R.image_from_memory(icon)
    reply = f'本群龙王是{dragon_nickname}' + icon
    await bot.send(event, reply)

update = sv.on_notice('notify.honor')
@update.handle()
async def _(bot: Bot, event: HonorNotifyEvent):
    global _dgk
    gid = event.group_id
    if event.honor_type == 'talkative':
        _dgk[gid] = event.user_id
