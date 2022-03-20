import re
from collections import defaultdict
from random import choice
from typing import Any, Dict, List

from hoshino import MessageSegment, Service, userdata_dir
from hoshino.permission import SUPERUSER
from hoshino.sres import Res as R
from hoshino.typing import Bot, GroupMessageEvent
from hoshino.util.sutil import download_async

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
            CustomReply.delete().where(CustomReply.word == x, CustomReply.matcher == self.matcher).execute()
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
        if len(event.message) == 0:
            return None
        msg = event.message[0]
        if msg.type == 'image':
            msg = msg.data['file']
        elif msg.type == 'text':
            msg = msg.data['text']
        else:
            msg = str(msg)
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
        if len(event.message) == 0:
            return None
        msg = event.message[0]
        if msg.type == 'image':
            msg = msg.data['file']
        elif msg.type == 'text':
            msg = msg.data['text']
        else:
            msg = str(msg)

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
        if len(event.message) == 0:
            return None
        msg = event.message[0]
        if msg.type == 'image':
            msg = msg.data['file']
        elif msg.type == 'text':
            msg = msg.data['text']
        else:
            msg = str(msg)
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
            await bot.send(event, reply)
            return
    else:
        pass

add_full = sv.on_command('fullmatch', permission=SUPERUSER)
add_key = sv.on_command('keyword', permission=SUPERUSER)
add_rex = sv.on_command('rex', permission=SUPERUSER)

data_dir = userdata_dir.joinpath('customreply').joinpath('data')
if not data_dir.exists():
    data_dir.mkdir(parents=True)

async def add_reply(bot: Bot, event: GroupMessageEvent):
    matcher = event.raw_message.strip().split()[0]
    start = event.message.pop(0)
    if start.type == 'text':
        tmp: List[str] = start.data['text'].strip().split()
        if len(tmp) == 2:
            word, reply = tmp[0], tmp[1]
        elif len(tmp) == 1:
            word, reply = tmp[0], ''
        
    elif start.type == 'image':
        word = start.data['file']
        reply = ''
    else:
        return # Todo: 其他类型的消息
    for m in event.message:
        if m.type == 'image':
            img = m.data['file'].replace('.image', '.jpg')
            url = m.data['url']
            # 下载图片存在本地
            await download_async(url, data_dir.joinpath(img))
            reply += f'【image: {img}】'

    try:
        handler: BaseHandler = eval(matcher)
        handler.add(word, reply)
        r = ['添加成功']
        r.extend(handler._dict[word])
        sv.logger.info(f'add {matcher} {word} {reply}')
        await bot.send(event, f'添加成功 {word}')
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
    matcher = event.raw_message.split()[1]
    msg = event.message[0]
    if msg.type == 'image':
        msg = msg.data['file']
    elif msg.type == 'text':
        msg = msg.data['text']
    else:
        msg = str(msg)
    handler: BaseHandler = eval(matcher)
    try:
        handler.delete(msg)
        await bot.send(event, '删除成功')
    except NotFoundException as ex:
        await bot.send(event, f'删除失败 {ex}')

del_full.handle()(delete_reply)
del_key.handle()(delete_reply)
del_rex.handle()(delete_reply)


@Bot.on_calling_api
async def handle_api_call(bot: Bot, api: str, data: Dict[str, Any]):
    if api != 'send_msg':
        return
    msgs: List[MessageSegment] = data['message']
    new_msg: List[MessageSegment] = []
    for msg in msgs:
        if msg.type != 'text':
            new_msg.append(msg)
            continue
        pics = re.findall(r'【image: (.*?)】', str(msg))
        if len(pics) == 0:
            new_msg.append(msg)
        for pic in pics:
            new_msg.append(R.image(f'data/customreply/data/{pic}'))
            sv.logger.info(f'replace {pic} with ')
    data['message'] = new_msg






