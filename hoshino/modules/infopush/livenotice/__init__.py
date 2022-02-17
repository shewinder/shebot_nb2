
from typing import List, Union

from hoshino import Service, Bot
from hoshino.typing import T_State, GroupMessageEvent

from hoshino.modules.infopush.checkers.bililive import BiliLiveChecker
from hoshino.modules.infopush.checkers.douyulive import DouyuLiveChecker
from .._model import BaseInfoChecker, SubscribeRecord

help_ = """
[直播订阅]
[删除直播订阅]
[查看直播订阅]
""".strip()

sv = Service('直播推送', help_=help_)

add_live = sv.on_command('live', aliases={'添加直播', '直播订阅'}, only_group=False)

@add_live.got('choice', prompt='请选择直播平台\n1: bilibili\n2: douyu')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        choice = int(state['choice']) - 1
    except:
        await add_live.reject('输入有误, 请重新输入')
    if choice == 0:
        state['checker'] = BiliLiveChecker
        state['url'] = f'https://api.live.bilibili.com/room/v1/Room/get_info?room_id='
    elif choice == 1:
        state['checker'] = DouyuLiveChecker
        state['url'] = f'http://open.douyucdn.cn/api/RoomApi/room/'
    
@add_live.got('room_id', prompt='请发送房间号')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    checker: BaseInfoChecker = state['checker']
    try:
        room_id = int(state['room_id'])
    except:
        await add_live.reject('输入有误, 请重新输入')
    url = state['url'] + str(room_id)
    state['url'] = url
    state['room_id'] = room_id

@add_live.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    checker: Union[BiliLiveChecker, DouyuLiveChecker] = state['checker']
    room_id = state['room_id']
    name = await checker.get_name_from_room(room_id)
    gid = event.group_id
    try:
        sub = checker.add_sub(gid, 
                              state['url'], 
                              remark=f'{name}开播',
                              creator_id=event.user_id)
        await add_live.finish(f'成功订阅{name}的直播间')
    except ValueError as e:
        await add_live.finish(str(e))

del_live = sv.on_command('del_live', aliases={'删除直播', '删除直播订阅'}, only_group=False)

@del_live.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    subs: List[SubscribeRecord] = BiliLiveChecker.get_creator_subs(event.group_id, event.user_id) \
                             + DouyuLiveChecker.get_creator_subs(event.group_id, event.user_id)
    lives = [f'{i+1}. {sub.remark}' for i,sub in enumerate(subs)]
    state['subs'] = subs
    await bot.send(event, '请发送对应序号选择取消的订阅\n' + '\n'.join(lives))



@del_live.got('choice')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        choice = int(state['choice']) - 1
        sub: SubscribeRecord  = state['subs'][choice]
    except:
        await del_live.reject('输入有误')
    chk: Union[BiliLiveChecker, DouyuLiveChecker] = eval(sub.checker)
    chk.delete_creator_sub(event.group_id, event.user_id, sub)
    await bot.send(event, f'已经删除{sub.remark}')


show_live = sv.on_command('show_live', aliases={'查看直播订阅', '查看直播', '看看订阅'}, only_group=False)
@show_live.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    subs: List[SubscribeRecord] = BiliLiveChecker.get_creator_subs(event.group_id, event.user_id) \
                             + DouyuLiveChecker.get_creator_subs(event.group_id, event.user_id)
    lives = [f'{i+1}. {sub.remark}' for i,sub in enumerate(subs)]
    await bot.send(event, '本群订阅如下\n' + '\n'.join(lives))   


