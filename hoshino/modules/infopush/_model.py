import asyncio
import os
from dataclasses import dataclass
from typing import Dict, List
import pickle

from pathlib import Path
from pydantic import BaseModel

from hoshino import glob
from hoshino import  get_bot_list, Bot
from hoshino.log import logger
from hoshino.glob import CHECKERS, SUBS
from hoshino.util.sutil import load_config, save_config

json_filepath = Path(__file__).parent.joinpath('subscribe')
pickle_filepath = Path(__file__).parent.joinpath('subscribe')

@dataclass
class SubscribeRecord:
    checker: str
    remark: str
    url: str
    date: str
    groups: List[int]
    users: List[int]

    def save(self):
        SUBS[self.checker][self.url] = self
        #save_config(SUBS, json_filepath)
        with open(pickle_filepath, 'wb') as f:
            pickle.dump(SUBS, f)

    def delete(self):
        sub = SUBS.get(self.checker, {}).get(self.url)
        if sub:
            del SUBS[self.checker][self.url]
            with open(pickle_filepath, 'wb') as f:
                pickle.dump(SUBS, f)
        else:
            raise ValueError('不存在该记录')

def load_subscribe(SUBS):
    try:
        with open(pickle_filepath, 'rb') as f:
            _subs = pickle.load(f)
            for k, v in _subs.items():
                SUBS[k] = v
    except FileNotFoundError:
        return None

@dataclass
class InfoData:
    """
    插件的info数据类应该继承此类
    """
    pub_time: str = None
    portal: str = None
    is_new: bool = True # 用于手动指定消息是否为新消息

class BaseInfoChecker:
    def __init__(self, seconds: int=120) -> None:
        """
        seconds 代表checker运行间隔秒数, 默认120s
        """
        self.seconds = seconds
        CHECKERS.append(self)

    @staticmethod
    def get_all_checkers() -> List["BaseInfoChecker"]:
        return CHECKERS

    @staticmethod
    def get_subscribe(checker_name: str, url: str) -> SubscribeRecord:
        return SUBS.get(checker_name, dict()).get(url, dict())

    @classmethod
    async def get_data(cls, url) -> InfoData:
        # 获取数据,插件应实现此抽象基类
        raise NotImplementedError

    @classmethod
    def get_group_subs(cls, group_id: int) -> List[SubscribeRecord]:
        _subs = []
        v = SUBS.get(cls.__name__, {})
        for vv in v.values():
            if group_id in vv.groups:
                _subs.append(vv)
        return _subs

    @classmethod
    def get_user_subs(cls, user_id: int) -> List[SubscribeRecord]:
        _subs = []
        v = SUBS.get(cls.__name__, {})
        for vv in v.values():
            if user_id in vv.users:
                _subs.append(vv)
        return _subs

    @classmethod
    def delete_group_sub(cls, group_id: int, sub: SubscribeRecord):
        if group_id in sub.groups:
            sub.groups.remove(group_id)
        if not sub.groups and not sub.users:
            sub.delete()
    
    @classmethod
    def delete_user_sub(cls, user_id: int, sub: SubscribeRecord):
        if user_id in sub.users:
            sub.users.remove(user_id)
        if not sub.users and not sub.groups:
            sub.delete()

    @classmethod
    def add_group(cls, group_id: int, checker: str, url: str, remark: str=None):
        sub = cls.get_subscribe(checker, url)
        if sub:
            if group_id in sub.groups:
                raise ValueError('重复订阅')
            sub.groups.append(group_id)
            sub.save()
        else:
            try:
                sub = SubscribeRecord(checker = checker,
                                      url = url,
                                      remark = remark,
                                      groups = [group_id],
                                      users = [],
                                      date = '')
                sub.save()
                return sub
            except Exception as e:
                logger.exception(e)
                raise ValueError(e)

    @classmethod
    def add_user(cls, user_id: int, checker: str, url: str, remark: str=None):
        sub = cls.get_subscribe(checker, url)
        if sub:
            if user_id in sub.users:
                raise ValueError('重复订阅')
            sub.users.append(user_id)
            sub.save()
        else:
            try:
                sub = SubscribeRecord(checker = checker,
                                      url = url,
                                      remark = remark,
                                      users = [user_id],
                                      groups = [],
                                      date = '')
                sub.save()
                return sub
            except Exception as e:
                logger.exception(e)
                raise ValueError(e)

    def notice_format(self, sub: SubscribeRecord, data: InfoData):
        """
        默认的通知排版格式，子类可重写此函数
        """
        return f'{sub.remark}更新啦！\n传送门{data.portal}'

    async def notice(self, sub: SubscribeRecord, data: InfoData):
        bot: Bot = get_bot_list()[0]
        for gid in sub.groups:
            try:
                gid = int(gid)
            except:
                continue
            try:
                await bot.send_group_msg(group_id=gid, 
                                         message=self.notice_format(sub, data))
            except Exception as e:
                logger.exception(e)
            await asyncio.sleep(0.5)
        for uid in sub.users:
            try:
                uid = int(uid)
            except:
                continue
            try:
                print(self.notice_format(sub, data))
                await bot.send_private_msg(user_id=uid, 
                                           message=self.notice_format(sub, data))
            except Exception as e:
                logger.exception(e)
            await asyncio.sleep(0.5)

    async def check_and_notice(self, sub: SubscribeRecord):
        data = await self.get_data(sub.url)
        if not data:
            logger.warning(f'检查{sub.checker}出错')
            return
        curr_date = data.pub_time
        if sub.date != curr_date and data.is_new:
            logger.info(f'检测到{sub.remark}更新')
            sub.date = curr_date
            sub.save()
            await self.notice(sub, data)
            return True
        else:
            return False
