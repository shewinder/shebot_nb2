from typing import List

from fastapi import APIRouter
from pydantic import BaseModel
from hoshino.modules.interactive.customreply.data import CustomReply
from hoshino.modules.interactive.customreply import fullmatch, keyword, rex, chain
import re

def reply_to_dict(record: CustomReply) -> dict:
    reply = re.sub(r'\[CQ:image,file=.+\]', '【图片】', record.reply)
    reply = re.sub(r'\[CQ:record,file=.+\]', '【语音】', reply)
    return {
        'word': record.word,
        'reply': reply,
        'matcher': record.matcher,
    }

def get_all_fullmatch() -> List[CustomReply]:
    return CustomReply.select().where(CustomReply.matcher == 'fullmatch')

def get_all_keyword() -> List[CustomReply]:
    return CustomReply.select().where(CustomReply.matcher == 'keyword')

def get_all_regex() -> List[CustomReply]:
    return CustomReply.select().where(CustomReply.matcher == 'regex')

def get_all() -> List[CustomReply]:
    return CustomReply.select()

def batch_delete(matcher: str, words: List[str]):
    CustomReply.delete().where(CustomReply.matcher == matcher, CustomReply.word.in_(words)).execute()
    for handler in chain:
        handler.refresh()

def edit_item(matcher: str, word: str, reply: str):
    CustomReply.update(reply=reply).where(CustomReply.matcher == matcher, CustomReply.word == word).execute()
    for handler in chain:
        if handler.matcher == matcher:
            handler.refresh()

router = APIRouter(prefix='/customreply')

@router.get('/list/fullmatch')
async def list_fullmatch():
    records = get_all_fullmatch()
    return {'records': [reply_to_dict(record) for record in records]}

@router.get('/list/keyword')
async def list_keyword():
    records = get_all_keyword()
    return {'records': [reply_to_dict(record) for record in records]}

@router.get('/list/regex')
async def list_regex():
    records = get_all_regex()
    return {'records': [reply_to_dict(record) for record in records]}

@router.get('/list/all')
async def list_all():
    records = get_all()
    return {'records': [reply_to_dict(record) for record in records]}

class DeleteItem(BaseModel):
    matcher: str
    words: List[str]

@router.post('/delete')
async def delete(form: DeleteItem):
    batch_delete(form.matcher, form.words)
    return {'status': 200, 'data': 'SUCCESS'}

class EditItem(BaseModel):
    matcher: str
    word: str
    reply: str

@router.post('/edit')
async def edit(item: EditItem):
    edit_item(item.matcher, item.word, item.reply)
    return {'status': 200, 'data': 'SUCCESS'}



