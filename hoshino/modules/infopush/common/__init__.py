from typing import List

from hoshino import Bot, Service
from hoshino.typing import T_State, GroupMessageEvent

from .._model import SubscribeRecord, BaseInfoChecker

help_ = """
[订阅] 添加一个订阅
[删除订阅]
[查看订阅]
""".strip()

_checkers = BaseInfoChecker.get_all_checkers()

sv = Service('订阅', help_=help_)

add_subscribe = sv.on_command('subscribe', aliases={'订阅'}, only_group=True)

async def choose(bot: Bot, event: GroupMessageEvent, state: T_State):
    if state['choice'] == 'cancel' or state['choice'] == '取消':
        await add_subscribe.finish('abort')
    try:
        choice = int(state['choice']) - 1
    except:
        await add_subscribe.reject('请输入数字, 重新输入')
    if choice < 0 or choice >= len(_checkers):
        await add_subscribe.reject('输入超限, 请重新输入')
    state['checker'] = _checkers[choice]

async def show_all(bot: Bot, event: GroupMessageEvent, state: T_State):
    msg = ['请发送对应序号选择订阅\n']
    for i, checker in enumerate(_checkers):
        msg.append(f'{i+1}. {checker.name}')
    msg.append('输入“取消”或者“cancel”退出')
    await bot.send(event, '\n'.join(msg))

add_subscribe.handle()(show_all)
add_subscribe.got('choice')(choose)
    

@add_subscribe.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    checker: BaseInfoChecker = state['checker']
    await bot.send(event, f'请发送{checker.distinguisher_name}')


@add_subscribe.got('dis')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    checker: BaseInfoChecker = state['checker']
    url = checker.form_url(state['dis'])
    try:
        data = await checker.get_data(url)
    except:
        data = None # 对于采用了ip池的checker，失败概率很高，暂不处理
    gid = event.group_id
    uid = event.user_id
    try:
        remark = checker.form_remark(data, state['dis'])
    except ValueError as e:
        await add_subscribe.finish('获取数据失败，请检查输入')
    try:
        checker.add_sub(gid, url, remark=remark, creator_id=uid)
        await add_subscribe.finish(f'成功订阅{remark}')
    except ValueError as e:
        await add_subscribe.finish(str(e))

del_subscribe = sv.on_command('del_subscribe', aliases={'删除订阅'}, only_group=True)

@del_subscribe.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    gid = event.group_id
    uid = event.user_id
    subs: List[SubscribeRecord] = []
    for checker in _checkers:
        subs.extend(checker.get_creator_subs(gid, uid))
    if not subs:
        await del_subscribe.finish('没有订阅')
    state['subs'] = subs
    msg = ['请发送对应序号选择订阅\n']
    for i, sub in enumerate(subs):
        msg.append(f'{i+1}. {sub.remark}')
    msg.append('输入“取消”或者“cancel”退出')
    await bot.send(event, '\n'.join(msg))

@del_subscribe.got('choice')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    subs: List[SubscribeRecord] = state['subs']
    try:
        choice = int(state['choice']) - 1
    except:
        await del_subscribe.reject('请输入数字, 重新输入')
    if choice < 0 or choice >= len(subs):
        await del_subscribe.reject('输入超限, 请重新输入')
    sub = subs[choice]
    sub.delete()
    await del_subscribe.finish(f'成功删除{sub.remark}')

show_subscribe = sv.on_command('show_subscribe', aliases={'查看订阅'}, only_group=True)

@show_subscribe.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    subs: List[SubscribeRecord] = []
    for checker in _checkers:
        subs.extend(checker.get_creator_subs(event.group_id, event.user_id))
    if not subs:
        await show_subscribe.finish('没有订阅')
    msg = ['你在本群的订阅如下\n']
    for sub in subs:
        msg.append(f'{sub.remark}')
    await bot.send(event, '\n'.join(msg))

