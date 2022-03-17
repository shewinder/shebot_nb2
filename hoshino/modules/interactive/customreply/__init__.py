import re
from collections import defaultdict
from random import choice
from typing import Dict, List

from hoshino import Service, Message
from hoshino.permission import SUPERUSER
from hoshino.typing import Bot, GroupMessageEvent

from .data import (CustomReply, ExistsException, KeywordConflictException,
                   NotFoundException)


class BaseHandler:

    def __init__(self, matcher: str) -> None:
        recs: List[CustomReply] = CustomReply.select().where(CustomReply.matcher == matcher)
        self._dict: Dict[str, List[str]] = defaultdict(list)
        self.matcher = matcher
        for rec in recs:
            if rec.word in self._dict:
                self._dict[rec.word].append(rec.reply)
            else:
                self._dict[rec.word] = [rec.reply]

    def delete(self, x: str) -> None:
        if x in self._dict:
            del self._dict[x]
            CustomReply.delete().where(CustomReply.word == x & CustomReply.matcher == self.matcher).execute()
        else:
            if not x:
                x = '<empty>'
            raise NotFoundException(f'{x} not found for {self.matcher}')

    def add(self, x: str, reply: str) -> None:
        raise  NotImplementedError

    def find_reply(self, event) -> str:
        raise NotImplementedError
 

class FullmatchHandler(BaseHandler):
    def __init__(self) -> None:
        super().__init__('fullmatch')

    def add(self, word: str, reply: str) -> None:
        if word in self._dict:
            if reply in self._dict[word]:
                raise ExistsException(f'reply {reply} already exists in fullmatch for {word}')
            self._dict[word].append(reply)
            #存入数据库
            CustomReply.create(word=word, reply=reply, matcher='fullmatch')
        else:
            self._dict[word] = [reply]
            CustomReply.create(word=word, reply=reply, matcher='fullmatch')

    def find_reply(self, event: GroupMessageEvent) -> str:
        msg = str(event.get_message()).strip()
        replys = self._dict.get(msg)
        if replys:
            return choice(replys)
        else:
            return None


class KeywordHandler(BaseHandler):
    def __init__(self) -> None:
        super().__init__('keyword')

    def add(self, keyword: str, reply: str) -> None:
        if keyword in self._dict:
            self._dict[keyword].append(reply)
            CustomReply.create(word=keyword, reply=reply, matcher='keyword')
            return True
        for k in self._dict:
            if keyword in k or k in keyword:
                raise KeywordConflictException(f'{keyword} conflicts with existed keyword {k}')
        self._dict[keyword] = [reply]
        CustomReply.create(word=keyword, reply=reply, matcher='keyword')

    def find_reply(self, event: GroupMessageEvent) -> str:
        msg = str(event.get_message()).strip()
        for k in self._dict:
            if k in msg:
                return choice(self._dict[k]) 
        return None

class RexHandler(BaseHandler):
    def __init__(self) -> None:
        super().__init__('rex')

    def add(self, pattern: str, reply: str) -> None:
        if pattern in self._dict:
            self._dict[pattern].append(reply)
            CustomReply.create(word=pattern, reply=reply, matcher='rex')
            return True
        self._dict[pattern] = [reply]
        CustomReply.create(word=pattern, reply=reply, matcher='rex')

    def find_reply(self, event: GroupMessageEvent) -> str:
        msg = str(event.get_message()).strip()
        for pattern in self._dict:
            match = re.search(pattern, msg)
            if match:
                reply = choice(self._dict[pattern])
                return reply


fullmatch = FullmatchHandler()
keyword = KeywordHandler()
rex = RexHandler()
chain: List[BaseHandler] = [fullmatch, keyword, rex]

sv = Service('自定义回复', visible=False)
custom = sv.on_message()

@custom.handle()
async def reply(bot: Bot, event: GroupMessageEvent):
    for h in chain:
        reply = h.find_reply(event)
        if reply:
            sv.logger.info(f'群{event.group_id} {event.user_id}({event.sender.nickname}) triggerd {h.matcher} reply {reply}')
            await bot.send(event, Message(reply))
            return
    else:
        pass

add_full = sv.on_command('fullmatch', permission=SUPERUSER)
add_key = sv.on_command('keyword', permission=SUPERUSER)
add_rex = sv.on_command('rex', permission=SUPERUSER)

async def add_reply(bot: Bot, event: GroupMessageEvent):
    matcher = event.raw_message.strip().split(' ')[0]
    word, reply = tuple(str(event.get_message()).strip().split(' '))
    try:
        handler: BaseHandler = eval(matcher)
        handler.add(word, reply)
        await bot.send(event, f'添加成功 {handler._dict[word]}')
    except (ExistsException, KeywordConflictException) as ex:
        await bot.send(event, f'添加失败，{ex}')
    except Exception as ex:
        sv.logger.error(ex)
        await bot.send(event, f'添加失败，{ex}')

add_full.handle()(add_reply)
add_key.handle()(add_reply)
add_rex.handle()(add_reply)

del_full = sv.on_command('del fullmatch', permission=SUPERUSER)
del_key = sv.on_command('del keyword', permission=SUPERUSER)
del_rex = sv.on_command('del rex', permission=SUPERUSER)

async def delete_reply(bot: Bot, event: GroupMessageEvent):
    matcher = event.raw_message.split(' ')[1]
    word: str = str(event.get_message()).strip()
    handler: BaseHandler = eval(matcher)
    try:
        handler.delete(word)
        await bot.send(event, '删除成功')
    except NotFoundException as vr:
        await bot.send(event, f'删除失败 {vr}')

del_full.handle()(delete_reply)
del_key.handle()(delete_reply)
del_rex.handle()(delete_reply)





