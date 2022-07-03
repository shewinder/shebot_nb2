'''
Author: AkiraXie
Date: 2021-01-28 02:32:32
LastEditors: AkiraXie
LastEditTime: 2021-02-02 23:48:55
Description: 
Github: http://github.com/AkiraXie/
'''

from hoshino.matcher import get_matchers
from hoshino.event import Event, get_event
from hoshino import Bot, get_bot_list, sucmd, MessageSegment, Message
test1 = sucmd('testgetbot', True)
test2 = sucmd('testmatchers', True)
test3 = sucmd('testevent', True)
test4 = sucmd('testnode', True)
test5 = sucmd('handle', True)


@test1.handle()
async def _(bot: Bot):
    await test1.finish(str(get_bot_list()))


@test2.handle()
async def _(bot: Bot):
    await test2.finish(str(get_matchers()))


@test3.handle()
async def _(bot: Bot, event: Event):
    await test3.finish(get_event(event))

@test4.handle()
async def _(bot: Bot, event: Event):
    from hoshino.util.message_util import send_group_forward_msg
    msgs1 = ["hello", MessageSegment.text("world")]
    #msgs1 = [Message("hello"), Message("world")]
    msgs2 = [msgs1]
    msgs3 = [msgs2]
    await send_group_forward_msg(bot, event.group_id, msgs1)
    # await send_group_forward_msg(bot, event.group_id, msgs2)
    # await send_group_forward_msg(bot, event.group_id, msgs3)

@test5.handle()
async def _(bot: Bot, event: Event):
    from nonebot.message import handle_event
    print('==========================', event)
    await handle_event(bot, event)
