
from typing import List
from nonebot.adapters.cqhttp import GroupMessageEvent

from hoshino import Service, Bot, Event, scheduled_job
from hoshino.log import logger
from hoshino.typing import T_State
from .data_source import BiliBiliLive, DouyuLive, Live, SubscribedLive

sv = Service('B站直播')
platforms = {0: 'bilibili', 1: 'douyu'}
bilibili = BiliBiliLive()
douyu = DouyuLive()


add_live = sv.on_command('live', aliases={'添加直播', '直播订阅'})

@add_live.got('choice', prompt='请选择直播平台\n0: bilibili\n1: douyu')
async def _(bot: Bot, event: Event, state: T_State):
    try:
        platform = platforms[int(state['choice'])]
        state['platform'] = platform
    except:
        add_live.reject('输入有误')
        raise

@add_live.got('room_id', prompt='请发送房间号')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    platform = state['platform']
    try:
        room_id = int(state['room_id'])
    except:
        add_live.reject('输入有误')

    if not await eval(platform).check_room_exists(room_id):
        await add_live.finish('未查询到该房间')

    name = await eval(platform).get_name_from_room(room_id)
    sub: SubscribedLive = SubscribedLive.get_or_none(SubscribedLive.platform == platform, SubscribedLive.room_id == room_id)
    if sub:
        groups = sub.groups.split(',')
        gid_str = str(event.group_id)
        if gid_str not in groups:
            groups.append(gid_str)
            sub.groups = ','.join(groups)
            sub.save()
            await add_live.finish(f'成功订阅{name}的直播间')
        else:
            await add_live.finish(f'本群已经订阅过{name}的直播间')

    else:
        sub = SubscribedLive.create(platform=platform, room_id=room_id, name=name, date='', groups=str(event.group_id))
        await add_live.finish(f'成功订阅{name}的直播间')

del_live = sv.on_command('del_live', aliases={'删除直播', '删除订阅'})

@del_live.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    subs = Live.get_group_subscrib(event.group_id)
    lives = [f'{i}. {sub.platform} {sub.name}' for i,sub in enumerate(subs)]
    state['subs'] = subs
    await bot.send(event, '请发送对应序号选择取消的订阅\n' + '\n'.join(lives))

@del_live.got('choice')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        choice = int(state['choice'])
        sub: SubscribedLive = state['subs'][choice]
    except:
        del_live.reject('输入有误')
    Live.delete_group_live(event.group_id, sub)
    await bot.send(event, f'已经删除{sub.name}的直播订阅')

show_live = sv.on_command('show_live', aliases={'查看直播订阅', '查看直播', '查看订阅', '看看订阅'})
@show_live.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    subs = Live.get_group_subscrib(event.group_id)
    lives = [f'{i}. {sub.platform} {sub.name}' for i,sub in enumerate(subs)]
    state['subs'] = subs
    await bot.send(event, '本群订阅如下\n' + '\n'.join(lives))   


@scheduled_job('interval', seconds=5, id='B站直播', max_instances=10)
async def _():
    sv.logger.info('start checking live')
    for v in platforms.values():
        await eval(v).check_update()
    sv.logger.info('checking live complete')
