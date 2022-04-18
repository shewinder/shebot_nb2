import aiohttp
from hoshino.sres import Res as R
from hoshino.message import Message

from .._model import BaseInfoChecker, SubscribeRecord, checker
from .._rss import RSS, RSSData

@checker
class TwitterChecker(BaseInfoChecker):
    seconds: int = 300
    name: str = '推特'
    distinguisher_name: str = "用户ID"

    @classmethod
    async def notice_format(cls, sub: SubscribeRecord, data: RSSData) -> Message:
        params = {"url": data.portal}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.shewinder.win/screenshot/twitter/article", params=params
            ) as resp:
                img = await resp.read()
        return f"{sub.remark}推特更新" + R.image_from_memory(img) + data.portal

    @classmethod
    async def get_data(self, url: str) -> RSSData:
        rss = RSS(url=url)
        await rss.get()
        return rss.parse_xml()

    @classmethod
    def form_url(cls, distinguisher: str) -> str:
        return RSS.from_route(f"twitter/media/{distinguisher}").url

    @classmethod
    def form_remark(cls, data: RSSData, distinguisher: str) -> str:
        return f"{data.author}推特"



