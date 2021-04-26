import asyncio
import json
import os
import abc
from typing import List

import aiohttp
from nonebot.adapters.cqhttp.message import MessageSegment
import peewee as pw
import requests

from hoshino.log import logger
from hoshino import db_dir, Bot, get_bot_list

PROXY_POOL_URL = 'http://140.143.122.138:5555/random'

def get_proxy():
    try:
        response = requests.get(PROXY_POOL_URL)
        if response.status_code == 200:
            return response.text
    except ConnectionError:
        return None


db_path = os.path.join(db_dir, 'live.db')
db = pw.SqliteDatabase(db_path)

class SubscribedLive(pw.Model):
    platform = pw.TextField()
    room_id = pw.TextField()
    name = pw.TextField()
    date = pw.TextField()
    groups = pw.TextField()
    users = pw.TextField()

    class Meta:
        database = db
        primary_key = pw.CompositeKey('platform', 'room_id')

if not os.path.exists(db_path):
    db.connect()
    db.create_tables([SubscribedLive])
    db.close()

class BaseLive:
    @property
    def platform(self):
        raise NotImplementedError

    def check_update():
        raise NotImplementedError

    def last_update():
        raise NotImplementedError

    @staticmethod
    async def notice(sub: SubscribedLive, title: str, url: str, cover: MessageSegment=None):
        bot: Bot = get_bot_list()[0]
        groups = sub.groups.split(',')
        users = sub.users.split(',')
        for gid in groups:
            try:
                gid = int(gid)
            except:
                continue
            try:
                if cover:
                    await bot.send_group_msg(group_id=gid, message=f'{sub.name}开播啦\n{title}\n{url}{cover}')
                else:
                    await bot.send_group_msg(group_id=gid, message=f'{sub.name}开播啦\n{title}\n{url}')
            except Exception as e:
                logger.exception(e)
            await asyncio.sleep(0.5)
        for uid in users:
            try:
                uid = int(uid)
            except:
                continue
            try:
                if cover:
                    await bot.send_private_msg(user_id=uid, message=f'{sub.name}开播啦\n{title}\n{url}{cover}')
                else:
                    await bot.send_private_msg(user_id=uid, message=f'{sub.name}开播啦\n{title}\n{url}')
            except Exception as e:
                logger.exception(e)
            await asyncio.sleep(0.5)

    @staticmethod
    def get_group_subscribe(group_id: int) -> List[SubscribedLive]:
        sql = pw.SQL('groups like ?', params=[f'%{group_id}%'])
        return SubscribedLive.select().where(sql)

    @staticmethod
    def get_user_subscribe(user_id: int) -> List[SubscribedLive]:
        sql = pw.SQL('users like ?', params=[f'%{user_id}%'])
        return SubscribedLive.select().where(sql)

    @staticmethod
    def delete_group_live(group_id: int, sub: SubscribedLive):
        groups: List[str] = sub.groups.split(',')
        if str(group_id) in groups:
            groups.remove(str(group_id))
            sub.groups = ','.join(groups)
            sub.save()
        if not groups and not sub.users:
            sub.delete_instance()

    @staticmethod
    def delete_user_live(user_id: int, sub: SubscribedLive):
        users: List[str] = sub.users.split(',')
        if str(user_id) in users:
            users.remove(str(user_id))
            sub.users = ','.join(users)
            sub.save()
        if not users and not sub.groups:
            sub.delete_instance()

    @staticmethod
    def add_group(group_id: int, platform: str, room_id: str):
        defaults = {
            'name': '',
            'groups': '',
            'users': '',
            'date': ''
        }
        sub, created = SubscribedLive.get_or_create(platform = platform, room_id = room_id, defaults=defaults)
        groups: List[str] = sub.groups.split(',')
        groups.remove('')
        if str(group_id) in groups:
            raise ValueError('duplicated group')
        groups.append(str(group_id))
        sub.groups = ','.join(groups)
        sub.save()

    @staticmethod
    def add_user(user_id: int, platform: str, room_id: str):
        defaults = {
            'name': '',
            'groups': '',
            'users': '',
            'date': ''
        }
        sub, created = SubscribedLive.get_or_create(platform = platform, room_id = room_id, defaults=defaults)
        users: List[str] = sub.users.split(',')
        users.remove('')
        if str(user_id) in users:
            raise ValueError('duplicated user')
        users.append(str(user_id))
        sub.users = ','.join(users)
        sub.save()

class BiliBiliLive(BaseLive):
    api_url = 'https://api.live.bilibili.com/room/v1/Room/get_info'

    @property
    def platform():
        return 'bilibili'
    
    @classmethod
    async def get_name_from_room(cls, room_id: int) -> dict:
        headers = {
            'Referer': 'https://link.bilibili.com/p/center/index',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36'
        }
        params = {
            'roomid': room_id
        } 
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get('https://api.live.bilibili.com/live_user/v1/UserInfo/get_anchor_in_room', 
                                        headers=headers, 
                                        params=params) as resp:
                    if resp.status == 200:
                        json_dic = await resp.json()
                        return json_dic['data']['info']['uname']
                    else:
                        logger.warning(f'未能成功获取主播名')
                        return 'unknown'
            except Exception as e:
                logger.exception(e)
                return 'unknown'

    @classmethod
    async def _get_bilibili_live_info(cls, room_id: int, use_proxy=False) -> dict:
        proxy = 'http://' + get_proxy() if use_proxy else None
        headers = {
            'Referer': 'https://link.bilibili.com/p/center/index',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36'
        }
        params = {
            'room_id': room_id
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(cls.api_url, headers=headers, params=params, proxy=proxy) as resp:
                    if resp.status == 200:
                        json_dic = await resp.json()
                        return json_dic
                    else:
                        logger.warning(f'访问B站直播发生错误，错误码{resp.status}')
            except Exception as e:
                #logger.exception(e)
                return {}

    async def check_update(self):
        # 根据直播时间检查所有直播间是否更新
        subs: List[SubscribedLive] = SubscribedLive.select().where(SubscribedLive.platform == 'bilibili')
        if not subs:
            logger.info('检查直播： 当前未订阅bilibili直播')
            return
        for sub in subs:
            resp = await self._get_bilibili_live_info(sub.room_id, use_proxy=True)
            if not resp:
                logger.warning(f'检查B站直播间{sub.room_id}出错')
                continue
            if resp['code'] != 0:
                logger.warning(f'检查B站直播间{sub.room_id}: {resp["message"]}')
                continue
            data = resp['data']
            # 刷新一次，防止多个任务同时推送
            sub = SubscribedLive.get_or_none(SubscribedLive.platform == 'bilibili', SubscribedLive.room_id == sub.room_id)
            if sub.date != data['live_time'] and data['live_status'] == 1:
                logger.info(f'检测到B站直播间{sub.room_id}更新')
                sub.date = data['live_time']
                sub.save()
                await self.notice(sub, 
                                  data['title'], 
                                  f'https://live.bilibili.com/{sub.room_id}', 
                                  MessageSegment.image(data['user_cover']))
    
    @classmethod
    async def check_room_exists(cls, room_id: int) -> bool:
        resp = await cls._get_bilibili_live_info(room_id)
        if resp:
            if resp['code'] == 0:
                return True
        return False

class DouyuLive(BaseLive):
    api_url = 'http://open.douyucdn.cn/api/RoomApi/room'

    @property
    def platform():
        return 'douyu'
    
    @classmethod
    async def get_name_from_room(cls, room_id: int) -> dict:
        headers = {
            'Referer': f'https://www.douyu.com/{room_id}',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36'
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f'{cls.api_url}/{room_id}', headers=headers) as resp:
                    if resp.status == 200:
                        json_dic = await resp.json()
                        return json_dic['data']['owner_name']
                    else:
                        logger.warning(f'未能成功获取主播名')
                        return 'unknown'
            except Exception as e:
                logger.exception(e)
                return 'unknown'

    @classmethod
    async def _get_douyu_live_info(cls, room_id: int, use_proxy=False) -> dict:
        proxy = 'http://' + get_proxy() if use_proxy else None
        headers = {
            'Referer': f'https://www.douyu.com/{room_id}',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36'
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f'{cls.api_url}/{room_id}', headers=headers, proxy=proxy) as resp:
                    if resp.status == 200:
                        json_dic = await resp.json()
                        return json_dic
                    else:
                        logger.warning(f'访问斗鱼直播发生错误，错误码{resp.status}')
            except Exception as e:
                #logger.exception(e)
                return {}

    async def check_update(self):
        # 根据直播时间检查所有直播间是否更新
        subs: List[SubscribedLive] = SubscribedLive.select().where(SubscribedLive.platform == 'douyu')
        if not subs:
            logger.info('检查直播： 当前未订阅douyu直播')
            return
        for sub in subs:
            last_date = sub.date
            resp = await self._get_douyu_live_info(sub.room_id, use_proxy=True)
            if not resp:
                logger.warning(f'检查斗鱼直播间{sub.room_id}出错')
                continue
            data = resp['data']
            # 刷新一次，防止多个任务同时推送
            sub = SubscribedLive.get_or_none(SubscribedLive.platform == 'douyu', SubscribedLive.room_id == sub.room_id)
            if last_date != data['start_time'] and data['room_status'] == '1':
                logger.info(f'检测到斗鱼直播间{sub.room_id}更新')
                sub.date = data['start_time']
                sub.save()
                await self.notice(sub, 
                                  data['room_name'], 
                                  f'https://www.douyu.com/{data["room_id"]}', 
                                  cover=MessageSegment.image(data['avatar']))
    
    @classmethod
    async def check_room_exists(cls, room_id: int) -> bool:
        data = await cls._get_douyu_live_info(room_id)
        return data 
        
