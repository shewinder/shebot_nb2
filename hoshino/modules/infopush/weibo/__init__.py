import aiohttp

from hoshino.modules.infopush.checkers.weibo import WeiboChecker
from nonebot.adapters.cqhttp import GroupMessageEvent
from hoshino import Service, Bot, Event
from hoshino.typing import T_State
from .._model import SubscribeRecord
from .._rss import RSS, RSSData

help_ = """
[微博订阅] 
[删除微博订阅]
[查看微博订阅]
""".strip()

sv = Service('微博订阅', help_=help_)

add_weibo = sv.on_command('weibo', aliases={'微博订阅', '添加微博订阅'}, only_group=False)

@add_weibo.got('mid', prompt='请发送博主ID')
async def _(bot: Bot, event: Event, state: T_State):
    try:
        mid = int(state['mid'])
    except:
        await add_weibo.finish('输入有误, 请重新输入')
    url = RSS(f'weibo/user/{mid}').url
    wb = await WeiboChecker.get_data(url)
    if not wb:
        await add_weibo.finish('未查询到该博主，请检查ID是否正确')
    state['url'] = url 
    state['weibo'] = wb

@add_weibo.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    w: RSSData = state['weibo']
    gid = event.group_id
    try:
        WeiboChecker.add_sub(gid, state['url'], remark=w.channel_title, creator_id=event.user_id)
        await add_weibo.finish(f'成功订阅{w.channel_title}')
    except ValueError as e:
        await add_weibo.finish(str(e))


del_weibo = sv.on_command('del_weibo', aliases={'删除微博订阅', '取消微博订阅'}, only_group=False)

@del_weibo.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    subs = WeiboChecker.get_creator_subs(event.group_id, event.user_id)
    reply = [f'{i+1}. {sub.remark}' for i,sub in enumerate(subs)]
    state['subs'] = subs
    await bot.send(event, '请发送对应序号选择取消的订阅\n' + '\n'.join(reply))

@del_weibo.got('choice')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        choice = int(state['choice']) -1
        sub: SubscribeRecord = state['subs'][choice]
    except:
        await del_weibo.finish('输入有误')
    WeiboChecker.delete_creator_sub(event.group_id, sub)
    await bot.send(event, f'已经删除{sub.remark}订阅')

show_weibo = sv.on_command('show_weibo', aliases={'查看微博订阅'}, only_group=False)
@show_weibo.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    subs = WeiboChecker.get_creator_subs(event.group_id, event.user_id)
    reply = [f'{i+1}. {sub.remark}' for i,sub in enumerate(subs)]
    await bot.send(event, '本群订阅如下\n' + '\n'.join(reply))   




