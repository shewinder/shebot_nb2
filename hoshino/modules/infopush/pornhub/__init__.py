import aiohttp
from nonebot.permission import SUPERUSER

from hoshino.modules.infopush.checkers.pornhub import Video
from nonebot.adapters.cqhttp import GroupMessageEvent, PrivateMessageEvent
from hoshino import Service, Bot, Event
from hoshino.typing import T_State
from .._model import SubscribeRecord
from hoshino.modules.infopush.checkers.pornhub import PornhubChecker, Video

sv = Service('Pornhub投稿', visible=False)

add_porn = sv.on_command('pornhubvideo', only_group=False, permission=SUPERUSER)

@add_porn.got('name', prompt='请发送UP名')
async def _(bot: Bot, event: Event, state: T_State):
    name = state['name']
    url = f'https://www.pornhub.com/users/{name}/videos'
    video = await PornhubChecker.get_data(url)
    if not video:
        await add_porn.finish('未查询到该UP，请检查UID是否正确')
    state['url'] = url 
    state['video'] = video

@add_porn.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    v: Video = state['video']
    gid = event.group_id
    try:
        PornhubChecker.add_group(gid, 'PornhubChecker', state['url'], remark=f'{state["name"]}投稿')
        await add_porn.finish(f'成功订阅{state["name"]}的投稿')
    except ValueError as e:
        await add_porn.finish(str(e))

@add_porn.handle()
async def _(bot: Bot, event: PrivateMessageEvent, state: T_State):
    v: Video = await PornhubChecker.get_data(state['url'])
    uid = event.user_id
    try:
        PornhubChecker.add_user(uid, 'PornhubChecker', state['url'], remark=f'{state["name"]}投稿')
        await add_porn.finish(f'成功订阅{state["name"]}的投稿')
    except ValueError as e:
        await add_porn.finish(str(e))


 


