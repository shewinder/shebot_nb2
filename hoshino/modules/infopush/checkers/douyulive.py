from asyncio.exceptions import TimeoutError
import aiohttp
import requests
from nonebot.adapters.cqhttp.message import MessageSegment

from hoshino.log import logger
from .._model import BaseInfoChecker, SubscribeRecord, InfoData
from .._config import plugin_config, Config

conf: Config = plugin_config.config

def get_proxy():
    try:
        response = requests.get(conf.PROXY_POOL_URL)
        if response.status_code == 200:
            return response.text
    except ConnectionError:
        return None

class DouyuLive(InfoData):
    title: str
    cover: str
    name: str

class DouyuLiveChecker(BaseInfoChecker):
    def notice_format(self, sub: SubscribeRecord , data: DouyuLive):
        return f'{sub.remark}啦！\n{data.title}'\
                + MessageSegment.image(data.cover)\
                + data.portal

    @classmethod
    async def get_name_from_room(cls, room_id):
        data = await cls.get_data(f'http://open.douyucdn.cn/api/RoomApi/room/{room_id}', False)
        return data.name

    @classmethod
    async def get_data(self, url, use_proxy: bool=False) -> DouyuLive:
        proxy = 'http://' + get_proxy() if use_proxy else None
        headers = {
            'Referer': f'https://www.douyu.com/{url.split("/")[-1]}',
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
                        lv = DouyuLive()
                        lv.pub_time = str(data['start_time'])
                        lv.portal = f'https://douyu.com/{data["room_id"]}'
                        lv.title = data['room_name']
                        lv.cover = data['room_thumb']
                        lv.name = data['owner_name']
                        lv.is_new = True if data['room_status'] == '1' else False # 用于判断是否正在开播, 防止订阅时推送历史开播信息
                        return lv
                    else:
                        logger.warning(f'访问{url}失败，status： {resp.status}')
                        return
            except TimeoutError:
                logger.warning('checking douyulive timeout')
            except Exception as e:
                #logger.exception(e)
                return None

    def form_url(self, dinstinguisher: str) -> str:
        return f'http://open.douyucdn.cn/api/RoomApi/room/' + dinstinguisher

    def form_remark(self, data: DouyuLive, distinguisher: str) -> str:
        return f'{data.name}直播'
DouyuLiveChecker(5, '斗鱼直播', '房间号')