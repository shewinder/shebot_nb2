import re
from collections import defaultdict
from random import choice
from typing import Any, Dict, List

from hoshino.sres import Res as R
from hoshino.typing import Bot, GroupMessageEvent

from ._data import (CustomReply, ExistsException, KeywordConflictException,
                   NotFoundException)


class BaseHandler:
    def __init__(self, matcher: str) -> None:
        self.matcher = matcher
        self.refresh()

    def refresh(self):
        recs: List[CustomReply] = CustomReply.select().where(
            CustomReply.matcher == self.matcher
        )
        self._dict: Dict[str, List[str]] = defaultdict(list)
        self.matcher = self.matcher
        for rec in recs:
            if rec.word in self._dict:
                self._dict[rec.word].append(rec.reply)
            else:
                self._dict[rec.word] = [rec.reply]

    def delete(self, x: str) -> None:
        if x in self._dict:
            del self._dict[x]
            CustomReply.delete().where(
                CustomReply.word == x, CustomReply.matcher == self.matcher
            ).execute()
        else:
            if not x:
                x = "<empty>"
            raise NotFoundException(f"{x} not found for {self.matcher}")

    def add(self, x: str, reply: str) -> None:
        raise NotImplementedError

    def find_reply(self, event) -> str:
        raise NotImplementedError


class FullmatchHandler(BaseHandler):
    def __init__(self) -> None:
        super().__init__("fullmatch")

    def add(self, word: str, reply: str) -> None:
        if word in self._dict and reply in self._dict[word]:
            raise ExistsException(
                f"reply {reply} already exists in fullmatch for {word}"
            )
        # 存入数据库
        CustomReply.create(word=word, reply=reply, matcher="fullmatch")
        # 刷新内存
        self.refresh()

    def find_reply(self, event: GroupMessageEvent) -> str:
        if len(event.message) == 0:
            return None
        msg = event.message[0]
        if msg.type == "image":
            msg = msg.data["file"]
        elif msg.type == "text":
            msg = msg.data["text"]
        else:
            msg = str(msg)
        replys = self._dict.get(msg)
        if replys:
            return choice(replys)
        else:
            return None


class KeywordHandler(BaseHandler):
    def __init__(self) -> None:
        super().__init__("keyword")

    def add(self, keyword: str, reply: str):
        if keyword in self._dict and reply == self._dict[keyword]:
            raise ExistsException(
                f"reply {reply} already exists in keyword for {keyword}"
            )
        CustomReply.create(word=keyword, reply=reply, matcher="keyword")
        self.refresh()

    def find_reply(self, event: GroupMessageEvent) -> str:
        if len(event.message) == 0:
            return None
        msg = event.message[0]
        if msg.type == "image":
            msg = msg.data["file"]
        elif msg.type == "text":
            msg = msg.data["text"]
        else:
            msg = str(msg)

        for k in self._dict:
            if k in msg:
                return choice(self._dict[k])
        return None


class RexHandler(BaseHandler):
    def __init__(self) -> None:
        super().__init__("rex")

    def add(self, pattern: str, reply: str):
        CustomReply.create(word=pattern, reply=reply, matcher="rex")
        self.refresh()

    def find_reply(self, event: GroupMessageEvent) -> str:
        if len(event.message) == 0:
            return None
        msg = event.message[0]
        if msg.type == "image":
            msg = msg.data["file"]
        elif msg.type == "text":
            msg = msg.data["text"]
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