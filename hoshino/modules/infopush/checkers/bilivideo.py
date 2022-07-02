import aiohttp
from hoshino import MessageSegment

from hoshino.log import logger
from hoshino.sres import Res as R
from .._model import BaseInfoChecker, InfoData, Subscribe

class Video(InfoData):
    title: str
    author: str
    cover: str
    description: str
    UID: str
    BV: str

class BiliVideoChecker(BaseInfoChecker):

    seconds: int = 120
    name: str = 'Bilibili投稿'
    distinguisher_name: str = "up ID"
    
    @classmethod
    async def notice_format(cls, sub: Subscribe , data: Video):
        return f'{sub.remark}更新啦！\n{data.title}'\
                + MessageSegment.image(data.cover)\
                + data.portal
                
    @classmethod
    async def get_data(cls, url: str) -> Video:
        headers = {
            'Referer': 'https://link.bilibili.com/p/center/index',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36'
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url=url, 
                                       headers=headers) as resp:
                    if resp.status == 200:
                        json_dic = await resp.json()
                        if 'list' not in json_dic['data']:
                            v= Video()
                            v.author = json_dic['data']['name']
                            return v
                        data = json_dic['data']['list']['vlist'][0]
                        v = Video()
                        v.pub_time = str(data['created'])
                        v.portal = f'https://www.bilibili.com/video/{data["bvid"]}'
                        v.title = data['title']
                        v.author = data['author']
                        v.cover = data['pic']
                        v.BV = data['bvid']
                        v.UID = data['mid']
                        return v
                    else:
                        logger.warning(f'访问{url}失败，status： {resp.status}')
                        return
            except Exception as e:
                logger.exception(e)
                return None

    @classmethod
    def form_url(cls, dinstinguisher: str) -> str:
        return f'https://api.bilibili.com/x/space/acc/info?mid={dinstinguisher}&jsonp=jsonp'
    
    @classmethod
    def form_remark(cls, data: Video, distinguisher: str) -> str:
        return f'{data.author}的投稿'
