import aiohttp

from hoshino.modules.infopush.checkers.bilivideo import Video
from hoshino import Service, Bot, Event, GroupMessageEvent
from hoshino.typing import T_State
from .._model import SubscribeRecord
from hoshino.modules.infopush.checkers.bilivideo import BiliVideoChecker, Video

help_ = """
[B站投稿订阅] B站投稿推送
""".strip()

sv = Service('B站投稿', help_=help_)

add_video = sv.on_command('bilivideo', aliases={'B站投稿订阅', 'B站投稿'}, only_group=False)

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
        BiliVideoChecker.add_sub(gid, state['url'], remark=f'{state["upname"]}投稿', creator_id=event.user_id)
        await add_video.finish(f'成功订阅{state["upname"]}的投稿')
    except ValueError as e:
        await add_video.finish(str(e))

del_video = sv.on_command('del_video', aliases={'删除B站投稿'}, only_group=False)

@del_video.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    subs = BiliVideoChecker.get_creator_subs(event.group_id, event.user_id)
    reply = [f'{i+1}. {sub.remark}' for i,sub in enumerate(subs)]
    state['subs'] = subs
    await bot.send(event, '请发送对应序号选择取消的订阅\n' + '\n'.join(reply))

@del_video.got('choice')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        choice = int(state['choice']) - 1
        sub: SubscribeRecord  = state['subs'][choice]
    except:
        del_video.reject('输入有误')
    BiliVideoChecker.delete_creator_sub(event.group_id, event.user_id, sub)
    await bot.send(event, f'已经删除{sub.remark}的投稿订阅')

show_live = sv.on_command('show_video', aliases={'查看投稿订阅'}, only_group=False)
@show_live.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    subs = BiliVideoChecker.get_creator_subs(event.group_id, event.user_id)
    reply = [f'{i+1}. {sub.remark}' for i,sub in enumerate(subs)]
    await bot.send(event, '本群订阅如下\n' + '\n'.join(reply))   




