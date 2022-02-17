from urllib.parse import urlencode, quote
import aiohttp
import urllib3
from hoshino import Bot, Event, Service
from hoshino.modules.infopush.checkers.pixivuser import (PixivData,
                                                         PixivUserChecker)
from hoshino.typing import T_State
from nonebot.adapters.cqhttp import GroupMessageEvent

from .._model import SubscribeRecord

help_ = """
[Pixiv投稿订阅] Pixiv投稿推送
[删除Pixiv投稿]
""".strip()

sv = Service('Pixiv投稿', help_=help_)

add_pixuser = sv.on_command('bilipixuser', aliases={'Pixiv投稿订阅', 'Pixiv投稿'}, only_group=True)


@add_pixuser.got('mid', prompt='请发送用户 ID')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        mid = int(state['mid'])
    except:
        await add_pixuser.reject('输入有误, 请重新输入')
    url = f'https://api.shewinder.win/pixiv/user?user_id={mid}'
    pixuserData = await PixivUserChecker.get_data(url)
    if not PixivData:
        await add_pixuser.finish('未查询到该用户，请检查UID是否正确')
    gid = event.group_id
    uid = event.user_id
    try:
        PixivUserChecker.add_sub(gid, url, remark=f'{pixuserData.user_name}插画', creator_id=uid)
        await add_pixuser.finish(f'成功订阅{pixuserData.user_name}的投稿')
    except ValueError as e:
        await add_pixuser.finish(str(e))

del_pixuser = sv.on_command('del_pixuser', aliases={'删除Pixiv投稿'}, only_group=True)

@del_pixuser.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    subs = PixivUserChecker.get_creator_subs(event.group_id, event.user_id)
    reply = [f'{i+1}. {sub.remark}' for i,sub in enumerate(subs)]
    state['subs'] = subs
    await bot.send(event, '请发送对应序号选择取消的订阅\n' + '\n'.join(reply))

@del_pixuser.got('choice')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        choice = int(state['choice']) - 1
        sub: SubscribeRecord  = state['subs'][choice]
    except:
        del_pixuser.reject('输入有误')
    PixivUserChecker.delete_creator_sub(event.group_id, event.user_id, sub)
    await bot.send(event, f'已经删除{sub.remark}的投稿订阅')

show_live = sv.on_command('show_pixuser', aliases={'查看Pixiv投稿订阅'}, only_group=False)
@show_live.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    subs = PixivUserChecker.get_creator_subs(event.group_id, event.user_id)
    reply = [f'{i+1}. {sub.remark}' for i,sub in enumerate(subs)]
    await bot.send(event, '本群订阅如下\n' + '\n'.join(reply))   




