import asyncio

from hoshino import Service, Bot
from hoshino.event import GroupMessageEvent
from hoshino.interact import interact, ActSession, SessionExistException
from hoshino.sres import Res as R
from .game import Game

wordle_sv = Service("wordle", enable_on_default=True)

start_game = wordle_sv.on_command(
    "猜单词", aliases={"猜词", "wordle"}, only_to_me=False, only_group=False
)
p_start_game = wordle_sv.on_command(
    "单人猜单词", aliases={"单人猜词", "单人wordle"}, only_to_me=False, only_group=True
)
check_word = wordle_sv.on_regex(
    r"([a-z]{5})", priority=3, block=False, only_group=False
)

@start_game.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    session = ActSession.from_event('wordle', event, usernum_limit=False)
    try:
        interact.create_session(session)
    except SessionExistException:
        await start_game.finish('已经有一个猜词游戏在进行中，请稍后再试')
    gm = Game()
    session.state['game'] = gm
    wordle_sv.logger.info(gm.answer)
    await bot.send(event, '游戏即将开始')
    await bot.send(event, R.image_from_memory(gm.image))

    await asyncio.sleep(300)
    ssn = interact.find_session_by_event(event) # 此处可能会获取到新的session导致结果不匹配
    if ssn and ssn.state['game'] == gm:
        ssn.close()
        await bot.send(event, "很遗憾，时间到了, 本次wordle已结束！答案是：" + gm.answer)

@interact.add_handler('wordle')
async def _(event: GroupMessageEvent, session: ActSession):
    ans = event.get_plaintext().strip().lower()
    if len(ans) != 5 or not ans.encode('UTF-8').isalpha():
        return
    gm: Game = session.state['game']
    if gm.check_word(ans):
        await session.finish(event, R.image_from_memory(gm.image) + f'恭喜你猜对了！正确答案为{gm.answer}')
    if gm.message:
        await session.send(event, gm.message)
        return
    if gm.cnt == 6:
        await session.finish(event, R.image_from_memory(gm.image) + f'很遗憾，你已经猜了6次了，正确答案为{gm.answer}')
    else:
        await session.send(event, R.image_from_memory(gm.image))