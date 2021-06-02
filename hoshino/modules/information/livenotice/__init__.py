
from typing import List
from nonebot.adapters.cqhttp import GroupMessageEvent, PrivateMessageEvent

from hoshino import Service, Bot, Event, scheduled_job
from hoshino.log import logger
from hoshino.typing import T_State
from .data_source import BiliBiliLive, DouyuLive, BaseLive, SubscribedLive

sv = Service('B站直播')
platforms = {0: 'bilibili', 1: 'douyu'}
bilibili = BiliBiliLive()
douyu = DouyuLive()


add_live = sv.on_command('live', aliases={'添加直播', '直播订阅'}, only_group=False)

@add_live.got('choice', prompt='请选择直播平台\n0: bilibili\n1: douyu')
async def _(bot: Bot, event: Event, state: T_State):
    try:
        platform = platforms[int(state['choice'])]
        state['platform'] = platform
    except:
        await add_live.reject('输入有误, 请重新输入')

@add_live.got('room_id', prompt='请发送房间号')
async def _(bot: Bot, event: Event, state: T_State):
    platform = state['platform']
    try:
        room_id = int(state['room_id'])
    except:
        await add_live.reject('输入有误, 请重新输入')

    if not await eval(platform).check_room_exists(room_id):
        await add_live.finish('未查询到该房间')
    state['room_id'] = room_id

@add_live.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    platform = state['platform']
    room_id = state['room_id']
    gid = event.group_id
    try:
        sub = await eval(platform).add_group(gid, platform, room_id)
        await add_live.finish(f'成功订阅{sub.name}的直播间')
    except ValueError as e:
        await add_live.finish(str(e))

@add_live.handle()
async def _(bot: Bot, event: PrivateMessageEvent, state: T_State):
    platform = state['platform']
    room_id = state['room_id']
    uid = event.user_id
    try:
        sub = await eval(platform).add_user(uid, platform, room_id)
        await add_live.finish(f'成功订阅{sub.name}的直播间')
    except ValueError as e:
        await add_live.finish(str(e))


del_live = sv.on_command('del_live', aliases={'删除直播', '删除直播订阅'}, only_group=False)

@del_live.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    subs = BaseLive.get_group_subscribe(event.group_id)
    lives = [f'{i}. {sub.platform} {sub.name}' for i,sub in enumerate(subs)]
    state['subs'] = subs
    await bot.send(event, '请发送对应序号选择取消的订阅\n' + '\n'.join(lives))

@del_live.handle()
async def _(bot: Bot, event: PrivateMessageEvent, state: T_State):
    subs = BaseLive.get_user_subscribe(event.user_id)
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
    BaseLive.delete_group_live(event.group_id, sub)
    await bot.send(event, f'已经删除{sub.name}的直播订阅')

@del_live.got('choice')
async def _(bot: Bot, event: PrivateMessageEvent, state: T_State):
    try:
        choice = int(state['choice'])
        sub: SubscribedLive = state['subs'][choice]
    except:
        del_live.reject('输入有误')
    BaseLive.delete_user_live(event.user_id, sub)
    await bot.send(event, f'已经删除{sub.name}的直播订阅')

show_live = sv.on_command('show_live', aliases={'查看直播订阅', '查看直播', '看看订阅'}, only_group=False)
@show_live.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    subs = BaseLive.get_group_subscribe(event.group_id)
    lives = [f'{i}. {sub.platform} {sub.name}' for i,sub in enumerate(subs)]
    await bot.send(event, '本群订阅如下\n' + '\n'.join(lives))   

@show_live.handle()
async def _(bot: Bot, event: PrivateMessageEvent):
    subs = BaseLive.get_user_subscribe(event.user_id)
    lives = [f'{i}. {sub.platform} {sub.name}' for i,sub in enumerate(subs)]
    await bot.send(event, '您的订阅如下\n' + '\n'.join(lives))   


@scheduled_job('interval', seconds=5, id='B站直播', max_instances=30)
async def _():
    sv.logger.info('start checking live')
    for v in platforms.values():
        await eval(v).check_update()
    sv.logger.info('checking live complete')
