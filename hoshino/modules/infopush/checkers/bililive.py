from asyncio.exceptions import TimeoutError

import aiohttp
import requests
from nonebot.adapters.cqhttp.message import MessageSegment

from hoshino.log import logger
from .._model import BaseInfoChecker, SubscribeRecord, InfoData

PROXY_POOL_URL = 'http://140.143.122.138:5555/random'

def get_proxy():
    try:
        response = requests.get(PROXY_POOL_URL)
        if response.status_code == 200:
            return response.text
    except ConnectionError:
        return None

class Live(InfoData):
    title: str
    cover: str

class BiliLiveChecker(BaseInfoChecker):
    def notice_format(self, sub: SubscribeRecord , data: Live):
        return f'{sub.remark}啦！\n{data.title}'\
                + MessageSegment.image(data.cover)\
                + data.portal
   
    @classmethod
    async def get_name_from_room(cls, room_id: int) -> str:
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
    async def get_data(self, url, use_proxy=True) -> Live:
        proxy = 'http://' + get_proxy() if use_proxy else None
        headers = {
            'Referer': 'https://link.bilibili.com/p/center/index',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36'
        }
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.get(url=url, 
                                       headers=headers,
                                       proxy=proxy) as resp:
                    if resp.status == 200:
                        json_dic = await resp.json()
                        data = json_dic['data']
                        lv = Live()
                        lv.pub_time = str(data['live_time'])
                        lv.portal = f'https://live.bilibili.com/{data["room_id"]}'
                        lv.title = data['title']
                        lv.cover = data['user_cover']
                        lv.is_new = True if data['live_status'] == 1 else False
                        return lv
                    else:
                        logger.warning(f'访问{url}失败，status： {resp.status}')
                        return
            except TimeoutError:
                logger.warning('checking bililive timeout')
            except Exception as e:
                #logger.exception(e)
                return None
BiliLiveChecker(5)