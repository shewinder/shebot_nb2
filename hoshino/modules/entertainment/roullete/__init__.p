from aiocqhttp.message import MessageSegment
from hoshino.service import Service
from hoshino.typing import Bot, GroupMessageEvent
from hoshino.interact import interact, ActSession
from random import randint, shuffle
from itertools import cycle

sv = Service('俄罗斯轮盘赌')
ru = sv.on_command('roullete', aliases={'轮盘赌', '俄罗斯轮盘赌'})

@ru.handle()
async def roulette(bot: Bot, event: GroupMessageEvent):
    try:
        session = ActSession.from_event('俄罗斯轮盘赌', event, max_user=6, usernum_limit=True)
        interact.create_session(session)
        await bot.send(event, '游戏开始,目前有1位玩家，至少2位玩家，发送"参与轮盘赌"加入游戏')
    except ValueError as e:
        await bot.finish(event, f'{e}')

join = sv.on_command('join roullete', aliases={'参与轮盘赌'})
async def join_roulette(bot: Bot, event: GroupMessageEvent):
    session = interact.find_session(event.group_id, name='俄罗斯轮盘赌')
    if not session:
        session = ActSession.from_event('俄罗斯轮盘赌', event, max_user=6, usernum_limit=True)
        await bot.send(event, '游戏开始,目前有1位玩家，至少2位玩家，发送"参与轮盘赌"加入游戏')
    try:
        interact.join_session(event, session)
        await bot.send(event, f'成功加入,目前有{session.count_user()}位玩家,发送“开始”进行游戏')
    except ValueError as e:
        await bot.send(event, str(e))

@interact.add_action('俄罗斯轮盘赌', (f'{MessageSegment.face(169)}', '开枪'))
async def fire(event: GroupMessageEvent, session: ActSession):
    if not session.state.get('started'):
        await session.finish(event, '请先发送“开始”进行游戏')

    if not session.pos:
        session.state['pos'] = randint(1, 6) #拨动轮盘，pos为第几发是子弹
    if not session.state.get('times'):
        session.state['times'] = 1

    if event.user_id != session.state.get('turn'):
        await session.send(event, '现在枪不在你手上哦~')
    
    pos = session.pos
    times = session.times
    if pos == times: #shoot
        session.close()
        await session.send(event, '枪响了，你死了！')
        await session.bot.se
    elif times == 5:
        session.close()
        user = session.rotate.__next__()
        await session.send(event, f'你长舒了一口气，并反手击毙了{MessageSegment.at(user)}')
        await session.bot.set_group_ban(group_id=event.group_id, user_id=user, duration=60)
    else:
        session.state['times'] += 1
        session.state['turn'] = session.rotate.__next__()
        await session.send(event, f'无事发生,轮到{MessageSegment.at(session.state["turn"])}开枪')

@interact.add_action('俄罗斯轮盘赌', '开始')
async def start_roulette(event: GroupMessageEvent, session: ActSession):
    if session.count_user() < 2:
        await session.finish(event, '人数不足')
        
    if not session.state.get('started'):
        session.state['started'] = True
        rule = """
        轮盘容量为6，但只填充了一发子弹，请参与游戏的双方轮流发送开枪，枪响结束
        """.strip()
        if not session.rotate: #user轮流
            shuffle(session.users)
            session.state['rotate'] = cycle(session.users)
        if not session.turn:
            session.state['turn'] = session.rotate.__next__()
        await session.send(event, f'游戏开始,{rule}现在请{MessageSegment.at(session.state["turn"])}开枪')
    else:
        await session.send(event, '游戏已经开始了')