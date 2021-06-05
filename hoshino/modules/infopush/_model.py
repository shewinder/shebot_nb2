import asyncio
import os
from dataclasses import dataclass
from typing import List

import peewee as pw

from hoshino import db_dir, get_bot_list, Bot
from hoshino.log import logger
from hoshino.glob import CHECKERS, SUBS

db_path = os.path.join(db_dir, 'info.db')
db = pw.SqliteDatabase(db_path)

class SubscribeRec(pw.Model):
    checker = pw.TextField()
    remark = pw.TextField()
    url = pw.TextField()
    date = pw.TextField()
    groups = pw.TextField()
    users = pw.TextField()

    class Meta:
        database = db
        primary_key = pw.CompositeKey('checker', 'url')

if not os.path.exists(db_path):
    db.connect()
    db.create_tables([SubscribeRec])
    db.close()

@dataclass
class InfoData:
    """
    插件的info数据类应该继承此类
    """
    pub_time: str = None
    portal: str = None

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

    @classmethod
    async def get_data(cls, url):
        # 获取数据,插件应实现此抽象基类
        raise NotImplementedError

    @classmethod
    def get_group_subs(cls, group_id: int) -> List[SubscribeRec]:
        return SubscribeRec.select().where((SubscribeRec.groups.contains(str(group_id))) 
            & (SubscribeRec.checker == cls.__name__))

    @classmethod
    def get_user_subs(cls, user_id: int) -> List[SubscribeRec]:
        return SubscribeRec.select().where((SubscribeRec.users.contains(str(user_id))) 
            & (SubscribeRec.checker == cls.__name__))

    @classmethod
    def delete_group_sub(cls, group_id: int, sub: SubscribeRec):
        groups: List[str] = sub.groups.split(',')
        if str(group_id) in groups:
            groups.remove(str(group_id))
            sub.groups = ','.join(groups)
            sub.save()
        if not groups and not sub.users:
            sub.delete_instance()
    
    @classmethod
    def delete_user_sub(cls, user_id: int, sub: SubscribeRec):
        users: List[str] = sub.users.split(',')
        if str(user_id) in users:
            users.remove(str(user_id))
            sub.users = ','.join(users)
            sub.save()
        if not users and not sub.groups:
            sub.delete_instance()

    @classmethod
    def add_group(cls, group_id: int, checker: str, url: str, remark: str=None):
        sub = SubscribeRec.get_or_none(checker = checker, url = url)
        if sub:
            groups: List[str] = sub.groups.split(',')
            if str(group_id) in groups:
                raise ValueError('重复订阅')
            groups.append(str(group_id))
            sub.groups = ','.join(groups)
            sub.save()
        else:
            try:
                sub = SubscribeRec.create(checker = checker,
                                          url = url,
                                          remark = remark,
                                          groups = str(group_id),
                                          users = '',
                                          date = '')
                SUBS[checker].append(sub)
                return sub
            except Exception as e:
                raise ValueError(e)

    @classmethod
    def add_user(cls, user_id: int, checker: str, url: str, remark: str=None):
        sub = SubscribeRec.get_or_none(checker  = checker, url = url)
        if sub:
            users: List[str] = sub.users.split(',')
            if str(user_id) in users:
                raise ValueError('重复订阅')
            users.append(str(user_id))
            sub.users = ','.join(users)
            sub.save()
        else:
            try:
                sub = SubscribeRec.create(checker = checker,
                                          url = url,
                                          remark = remark,
                                          users = str(user_id),
                                          groups = '',
                                          date = '')
                SUBS[checker].append(sub)
                return sub
            except Exception as e:
                raise ValueError(e)

    def notice_format(self, sub, data):
        """
        默认的通知排版格式，子类可重写此函数
        """
        return f'{sub.remark}更新啦！\n传送门{data.portal}'

    async def notice(self, sub: SubscribeRec, data: InfoData):
        bot: Bot = get_bot_list()[0]
        groups = sub.groups.split(',')
        users = sub.users.split(',')
        for gid in groups:
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
        for uid in users:
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

    async def check_and_notice(self, sub: SubscribeRec):
        data: InfoData = await self.get_data(sub.url)
        if not data:
            logger.warning(f'检查{sub.checker}出错')
            return
        curr_date = data.pub_time
        if sub.date != curr_date:
            logger.info(f'检测到{sub.remark}更新')
            sub.date = curr_date
            sub.save()
            await self.notice(sub, data)
            return True
        else:
            return False
