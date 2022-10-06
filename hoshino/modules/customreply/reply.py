import re
from collections import defaultdict
from random import choice
from typing import Any, Dict, List

from hoshino import Message, MessageSegment, Service, T_State, userdata_dir
from hoshino.permission import SUPERUSER
from hoshino.sres import Res as R
from hoshino.typing import Bot, GroupMessageEvent
from hoshino.util import aiohttpx

from ._data import (
    CustomReply,
    ExistsException,
    KeywordConflictException,
    NotFoundException,
)
from ._handler import BaseHandler, chain, fullmatch, rex, keyword

sv = Service("自定义回复", visible=False)
custom = sv.on_message()


@custom.handle()
async def reply(bot: Bot, event: GroupMessageEvent):
    for h in chain:
        reply = h.find_reply(event)
        if reply:
            sv.logger.info(
                f"群{event.group_id} {event.user_id} triggerd matcher: {h.matcher} reply: {reply[:10]}"
            )
            await bot.send(event, Message(reply))
            return
    else:
        pass


add_full = sv.on_command("fullmatch", permission=SUPERUSER)
add_key = sv.on_command("keyword", permission=SUPERUSER)
add_rex = sv.on_command("rex", permission=SUPERUSER)

data_dir = userdata_dir.joinpath("customreply").joinpath("data")
if not data_dir.exists():
    data_dir.mkdir(parents=True)


async def handler1(bot: Bot, event: GroupMessageEvent, state: T_State):
    matcher = event.raw_message.strip().split()[0]
    word, reply = "", ""
    start = event.message.pop(0)

    if start.type == "text":
        tmp: List[str] = start.data["text"].strip().split()
        if len(tmp) == 2:
            word, reply = tmp[0], tmp[1]
        elif len(tmp) == 1:
            word, reply = tmp[0], ""

    elif start.type == "image":
        word = start.data["file"]
        reply = ""
    else:
        return  # Todo: 其他类型的消息
    for m in event.message:
        if m.type == "image":
            url = m.data["url"]
            reply += await R.image_from_url(url)

    if not word:
        return
    state["matcher"] = matcher
    state["word"] = word
    if reply:
        state["reply"] = reply
        state["special"] = False  # a flag to indicate that this is a special reply


async def handler2(bot: Bot, event: GroupMessageEvent, state: T_State):
    """
    处理无法在一条消息中完成的情况，例如reply为语音
    """
    if state["special"] == False:
        return

    msg = event.message[0]
    if msg.type == "record":
        rec_url = msg.data["url"]
        resp = await aiohttpx.get(rec_url)
        rec_bytes = resp.content
        state["reply"] = MessageSegment.record(rec_bytes)


async def handler3(bot: Bot, event: GroupMessageEvent, state: T_State):
    matcher = state["matcher"]
    word = state["word"]
    reply = state["reply"]
    if not reply:
        return
    try:
        handler: BaseHandler = eval(matcher)
        handler.add(word, reply)
        r = ["添加成功"]
        r.extend(handler._dict[word])
        sv.logger.info(f"add {matcher} {word} ")
        await bot.send(event, f"添加成功 {word}")
    except (ExistsException, KeywordConflictException) as ex:
        await bot.send(event, f"添加失败，{ex}")
    except Exception as ex:
        sv.logger.error(ex)
        await bot.send(event, f"添加失败，{ex}")


add_full.handle()(handler1)
add_key.handle()(handler1)
add_rex.handle()(handler1)

add_full.got("special")(handler2)
add_key.got("special")(handler2)
add_rex.got("special")(handler2)

add_full.handle()(handler3)
add_key.handle()(handler3)
add_rex.handle()(handler3)

del_full = sv.on_command("del fullmatch", permission=SUPERUSER)
del_key = sv.on_command("del keyword", permission=SUPERUSER)
del_rex = sv.on_command("del rex", permission=SUPERUSER)


async def delete_reply(bot: Bot, event: GroupMessageEvent):
    matcher = event.raw_message.split()[1]
    msg = event.message[0]
    if msg.type == "image":
        msg = msg.data["file"]
    elif msg.type == "text":
        msg = msg.data["text"]
    else:
        msg = str(msg)
    handler: BaseHandler = eval(matcher)
    try:
        handler.delete(msg)
        await bot.send(event, "删除成功")
    except NotFoundException as ex:
        await bot.send(event, f"删除失败 {ex}")


del_full.handle()(delete_reply)
del_key.handle()(delete_reply)
del_rex.handle()(delete_reply)
