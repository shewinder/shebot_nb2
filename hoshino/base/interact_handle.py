from hoshino.service import on_message

from hoshino.interact import interact, ActSession, SessionFinishedException
from hoshino.log import logger
from hoshino.typing import Bot, GroupMessageEvent, T_State

inter = on_message()

@inter.handle()
async def handler_interaction(bot: Bot, event: GroupMessageEvent, state: T_State):
    session = interact.find_session_by_event(event)
    if not session:
        return

    if event.raw_message in ('exit', 'quit') and event.user_id == session.creator: #创建者选择退出
        session.close()
        logger.info(f'session {session.name} quit by creator')
        await session.finish(event, f'{session.name}已经结束，欢迎下次再玩！')

    if session.is_expire():
        session.close()

    action_func = session.actions.get(event.raw_message) if event.user_id in session.users else None
    if action_func:
        logger.info(f'triggered interaction action {action_func.__name__}')
        try:
            await action_func(event, session)
        except Exception as ex:
            logger.exception(ex)
    
    handlers = session.handlers()
    for handler in handlers:
        try:
            await handler(event, session)
        except SessionFinishedException:
            break