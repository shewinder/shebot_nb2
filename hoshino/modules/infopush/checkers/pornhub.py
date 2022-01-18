import json
import aiohttp
from nonebot.adapters.cqhttp.message import MessageSegment

from hoshino.log import logger
from hoshino.sres import Res as R
from .._model import BaseInfoChecker, InfoData, SubscribeRecord
from lxml import etree

class Video(InfoData):
    title: str
    author: str
    cover: str

class PornhubChecker(BaseInfoChecker):
    def notice_format(self, sub: SubscribeRecord , data: Video):
        return f'{sub.remark}更新啦！\n{data.title}'\
                + MessageSegment.image(data.cover)
                
    @classmethod
    async def get_data(self, url: str) -> Video:
        headers = {
            'Referer': 'https://pornhub.com',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36'
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url='http://23.224.81.98:9053/forwarder/',
                                        headers = {'content_type': 'application/json'},
                                        json = {
                                           'url': url,
                                           "method": 'get'
                                       }
                                       ) as resp:
                    if resp.status == 200:
                        t = await resp.text()
                        html = etree.HTML(t)
                        li = html.xpath('//ul[@id="modelMostRecentVideosSection"]/li')
                        a = li[0].xpath('./div/div/a')[0]
                        img = li[0].xpath('./div/div/a/img')[0]
                        v = Video()
                        v.pub_time = img.attrib['data-video-id'] # 以id代替时间
                        v.title = a.attrib['title']
                        v.author = url.split('/')[-2]
                        v.cover = img.attrib['data-thumb_url']
                        return v
                    else:
                        logger.warning(f'访问{url}失败，status： {resp.status}')
                        return
            except Exception as e:
                logger.exception(e)
                return None
#PornhubChecker(600)