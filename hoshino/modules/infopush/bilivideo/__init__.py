import aiohttp

from hoshino.modules.infopush.checkers.bilivideo import Video
from nonebot.adapters.cqhttp import GroupMessageEvent, PrivateMessageEvent
from hoshino import Service, Bot, Event
from hoshino.typing import T_State
from .._model import SubscribeRec
from hoshino.modules.infopush.checkers.bilivideo import BiliVideoChecker, Video

sv = Service('B站投稿')

add_video = sv.on_command('bilivideo', aliases={'添加B站投稿推送', 'B站投稿'}, only_group=False)

async def get_name_from_uid(uid: int):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://api.bilibili.com/x/space/acc/info?mid={uid}&jsonp=jsonp') as resp:
            if resp.status == 200:
                json_dic = await resp.json()
                return json_dic['data']['name']

@add_video.got('mid', prompt='请发送UP UID')
async def _(bot: Bot, event: Event, state: T_State):
    try:
        mid = int(state['mid'])
    except:
        await add_video.reject('输入有误, 请重新输入')
    url = f'https://api.bilibili.com/x/space/arc/search?mid={mid}&ps=1&tid=0&pn=1&order=pubdate&jsonp=jsonp'
    video = await BiliVideoChecker.get_data(url)
    if not video:
        await add_video.finish('未查询到该UP，请检查UID是否正确')
    upname = await get_name_from_uid(mid)
    state['url'] = url 
    state['video'] = video
    state['upname'] = upname

@add_video.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    v: Video = state['video']
    gid = event.group_id
    try:
        BiliVideoChecker.add_group(gid, 'BiliVideoChecker', state['url'], remark=f'{state["upname"]}投稿')
        await add_video.finish(f'成功订阅{state["upname"]}的投稿')
    except ValueError as e:
        await add_video.finish(str(e))

@add_video.handle()
async def _(bot: Bot, event: PrivateMessageEvent, state: T_State):
    v: Video = await BiliVideoChecker.get_data(state['url'])
    uid = event.user_id
    try:
        BiliVideoChecker.add_user(uid, 'BiliVideoChecker', state['url'], remark=f'{state["upname"]}投稿')
        await add_video.finish(f'成功订阅{state["upname"]}的投稿')
    except ValueError as e:
        await add_video.finish(str(e))


del_video = sv.on_command('del_video', aliases={'删除B站投稿'}, only_group=False)

@del_video.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    subs = BiliVideoChecker.get_group_subs(event.group_id)
    reply = [f'{i}. {sub.remark}' for i,sub in enumerate(subs)]
    state['subs'] = subs
    await bot.send(event, '请发送对应序号选择取消的订阅\n' + '\n'.join(reply))

@del_video.handle()
async def _(bot: Bot, event: PrivateMessageEvent, state: T_State):
    subs = BiliVideoChecker.get_user_subs(event.user_id)
    reply = [f'{i}. {sub.remark}' for i,sub in enumerate(subs)]
    state['subs'] = subs
    await bot.send(event, '请发送对应序号选择取消的订阅\n' + '\n'.join(reply))

@del_video.got('choice')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        choice = int(state['choice'])
        sub: SubscribeRec = state['subs'][choice]
    except:
        del_video.reject('输入有误')
    BiliVideoChecker.delete_group_sub(event.group_id, sub)
    await bot.send(event, f'已经删除{sub.name}的投稿订阅')

@del_video.got('choice')
async def _(bot: Bot, event: PrivateMessageEvent, state: T_State):
    try:
        choice = int(state['choice'])
        sub: SubscribeRec = state['subs'][choice]
    except:
        await del_video.finish('输入有误')
    BiliVideoChecker.delete_user_sub(event.user_id, sub)
    await bot.send(event, f'已经删除{sub.remark}的投稿订阅')

show_live = sv.on_command('show_video', aliases={'查看投稿订阅'}, only_group=False)
@show_live.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    subs = BiliVideoChecker.get_group_subs(event.group_id)
    reply = [f'{i}. {sub.remark}' for i,sub in enumerate(subs)]
    await bot.send(event, '本群订阅如下\n' + '\n'.join(reply))   

@show_live.handle()
async def _(bot: Bot, event: PrivateMessageEvent):
    subs = BiliVideoChecker.get_user_subs(event.user_id)
    reply = [f'{i}. {sub.remark}' for i,sub in enumerate(subs)]
    await bot.send(event, '您的订阅如下\n' + '\n'.join(reply))   

