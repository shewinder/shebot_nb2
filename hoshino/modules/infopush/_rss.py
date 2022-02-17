from typing import Dict
import aiohttp
from lxml import etree
from ._model import InfoData

class RSS:
    def __init__(self, route: str=None, url: str=None):
        self.base_url = 'http://43.134.194.249:1200/'
        self.route = route
        self.xml : bytes = None
        self.limit = 1
        self.url = url if url else self.base_url + self.route

    async def get(self):
        url = self.url
        params = {}
        params['limit'] = self.limit
        async with aiohttp.ClientSession() as session:
            async with session.get(url,params=params) as resp:
                self.xml = await resp.read()

    def parse_xml(self) -> Dict:
        rss = etree.XML(self.xml)
        channel = rss.xpath('/rss/channel')[0]
        channel_title = channel.find('.title').text.strip()
        item = rss.xpath('/rss/channel/item')[0]
        title = item.find('.title').text.strip()
        desc = item.find('.description').text.strip()
        link = item.find('.link').text.strip()
        pubDate = item.find('.pubDate').text.strip()
        return {
            "title" : title,
            "desc" : desc,
            "link" : link,
            "pubDate" : pubDate,
            "channel_title": channel_title
        }