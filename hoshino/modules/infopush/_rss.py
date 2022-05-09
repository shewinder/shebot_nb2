import aiohttp
from lxml import etree


from ._config import Config
from ._model import InfoData

conf: Config = Config.get_instance("infopush")


class RSSData(InfoData):
    title: str = ""
    desc: str = ""
    channel_title: str = ""
    author: str = ""


class RSS:
    def __init__(self, url: str):
        self.xml: bytes = None
        self.limit = 1
        self.url = url

    @classmethod
    def from_route(cls, route: str) -> "RSS":
        if not conf.rsshub_url.endswith("/"):
            return RSS(conf.rsshub_url + "/" + route)
        return RSS(conf.rsshub_url + route)

    async def get(self):
        url = self.url
        params = {}
        params["limit"] = self.limit
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                self.xml = await resp.read()

    def parse_xml(self) -> RSSData:
        rss = etree.XML(self.xml)
        d = RSSData()
        channel = rss.xpath("/rss/channel")[0]
        d.channel_title = channel.find(".title").text.strip()
        item = rss.xpath("/rss/channel/item")[0]
        d.title = item.find(".title").text.strip()
        d.desc = item.find(".description").text.strip()
        d.portal = item.find(".link").text.strip()
        d.pub_time = item.find(".pubDate").text.strip()
        d.author = item.find(".author").text.strip()
        return d
