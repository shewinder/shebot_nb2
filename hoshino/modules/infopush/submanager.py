from nonebot.adapters.cqhttp import GroupMessageEvent, PrivateMessageEvent

from hoshino import Service, Bot, sucmd
from hoshino.typing import T_State
from ._model import SubscribeRecord, BaseInfoChecker
from ._glob import CHECKERS

sv = Service('推送管理')

del_sub = sucmd('del_sub', aliases={'删除推送'})

@del_sub.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    subs = []
    for chk in CHECKERS:
        subs += chk.get_group_subs(event.group_id)
    reply = [f'{i+1}. {sub.remark}' for i,sub in enumerate(subs)]
    state['subs'] = subs
    await bot.send(event, '请发送对应序号选择取消的订阅\n' + '\n'.join(reply))

@del_sub.handle()
async def _(bot: Bot, event: PrivateMessageEvent, state: T_State):
    subs = []
    for chk in CHECKERS:
        subs += chk.get_user_subs(event.user_id)
    reply = [f'{i+1}. {sub.remark}' for i,sub in enumerate(subs)]
    state['subs'] = subs
    await bot.send(event, '请发送对应序号选择取消的订阅\n' + '\n'.join(reply))

@del_sub.got('choice')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        choice = int(state['choice']) - 1
        sub: SubscribeRecord  = state['subs'][choice]
    except:
        del_sub.reject('输入有误')
    BaseInfoChecker.delete_group_sub(event.group_id, sub)
    await bot.send(event, f'已经删除{sub.remark}的推送')

@del_sub.got('choice')
async def _(bot: Bot, event: PrivateMessageEvent, state: T_State):
    try:
        choice = int(state['choice']) - 1
        sub: SubscribeRecord  = state['subs'][choice]
    except:
        await del_sub.finish('输入有误')
    BaseInfoChecker.delete_user_sub(event.user_id, sub)
    await bot.send(event, f'已经删除{sub.remark}的推送')

show_sub = sucmd('show_sub', aliases={'查看推送'})
@show_sub.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    subs = []
    for chk in CHECKERS:
        subs += chk.get_group_subs(event.group_id)
    reply = [f'{i+1}. {sub.remark}' for i,sub in enumerate(subs)]
    await bot.send(event, '本群订阅如下\n' + '\n'.join(reply))   

@show_sub.handle()
async def _(bot: Bot, event: PrivateMessageEvent):
    subs = []
    for chk in CHECKERS:
        subs += chk.get_user_subs(event.user_id)
    reply = [f'{i+1}. {sub.remark}' for i,sub in enumerate(subs)]
    await bot.send(event, '您的订阅如下\n' + '\n'.join(reply))   


