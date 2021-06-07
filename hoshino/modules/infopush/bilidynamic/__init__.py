import aiohttp

from hoshino.modules.infopush.checkers.bilidynamic import BiliDynamicChecker, Dynamic
from nonebot.adapters.cqhttp import GroupMessageEvent, PrivateMessageEvent
from hoshino import Service, Bot, Event
from hoshino.typing import T_State
from .._model import SubscribeRecord

sv = Service('B站动态')

add_dynamic = sv.on_command('bilidynamic', aliases={'添加B站动态推送', 'B站动态'}, only_group=False)

async def get_name_from_uid(uid: int):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://api.bilibili.com/x/space/acc/info?mid={uid}&jsonp=jsonp') as resp:
            if resp.status == 200:
                json_dic = await resp.json()
                return json_dic['data']['name']

@add_dynamic.got('mid', prompt='请发送UP UID')
async def _(bot: Bot, event: Event, state: T_State):
    try:
        mid = int(state['mid'])
    except:
        await add_dynamic.finish('输入有误, 请重新输入')
    url = f'https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history?host_uid={mid}'
    dynamic = await BiliDynamicChecker.get_data(url)
    if not dynamic:
        await add_dynamic.finish('未查询到该UP，请检查UID是否正确')
    upname = await get_name_from_uid(mid)
    state['url'] = url 
    state['dynamic'] = dynamic
    state['upname'] = upname

@add_dynamic.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    v: Dynamic = state['dynamic']
    gid = event.group_id
    try:
        BiliDynamicChecker.add_group(gid, 'BiliDynamicChecker', state['url'], remark=f'{state["upname"]}动态')
        await add_dynamic.finish(f'成功订阅{state["upname"]}的动态')
    except ValueError as e:
        await add_dynamic.finish(str(e))

@add_dynamic.handle()
async def _(bot: Bot, event: PrivateMessageEvent, state: T_State):
    v: Dynamic = await BiliDynamicChecker.get_data(state['url'])
    uid = event.user_id
    try:
        BiliDynamicChecker.add_user(uid, 'BiliDynamicChecker', state['url'], remark=f'{state["upname"]}动态')
        await add_dynamic.finish(f'成功订阅{state["upname"]}的动态')
    except ValueError as e:
        await add_dynamic.finish(str(e))


del_dynamic = sv.on_command('del_dynamic', aliases={'删除B站动态'}, only_group=False)

@del_dynamic.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    subs = BiliDynamicChecker.get_group_subs(event.group_id)
    reply = [f'{i}. {sub.remark}' for i,sub in enumerate(subs)]
    state['subs'] = subs
    await bot.send(event, '请发送对应序号选择取消的订阅\n' + '\n'.join(reply))

@del_dynamic.handle()
async def _(bot: Bot, event: PrivateMessageEvent, state: T_State):
    subs = BiliDynamicChecker.get_user_subs(event.user_id)
    reply = [f'{i}. {sub.remark}' for i,sub in enumerate(subs)]
    state['subs'] = subs
    await bot.send(event, '请发送对应序号选择取消的订阅\n' + '\n'.join(reply))

@del_dynamic.got('choice')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        choice = int(state['choice'])
        sub: SubscribeRecord = state['subs'][choice]
    except:
        await del_dynamic.finish('输入有误')
    BiliDynamicChecker.delete_group_sub(event.group_id, sub)
    await bot.send(event, f'已经删除{sub.name}的动态订阅')

@del_dynamic.got('choice')
async def _(bot: Bot, event: PrivateMessageEvent, state: T_State):
    try:
        choice = int(state['choice'])
        sub: SubscribeRecord = state['subs'][choice]
    except:
        await del_dynamic.finish('输入有误')
    BiliDynamicChecker.delete_user_sub(event.user_id, sub)
    await bot.send(event, f'已经删除{sub.remark}的动态订阅')

show_live = sv.on_command('show_dynamic', aliases={'查看动态订阅'}, only_group=False)
@show_live.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    subs = BiliDynamicChecker.get_group_subs(event.group_id)
    reply = [f'{i}. {sub.remark}' for i,sub in enumerate(subs)]
    await bot.send(event, '本群订阅如下\n' + '\n'.join(reply))   

@show_live.handle()
async def _(bot: Bot, event: PrivateMessageEvent):
    subs = BiliDynamicChecker.get_user_subs(event.user_id)
    reply = [f'{i}. {sub.remark}' for i,sub in enumerate(subs)]
    await bot.send(event, '您的订阅如下\n' + '\n'.join(reply))   


