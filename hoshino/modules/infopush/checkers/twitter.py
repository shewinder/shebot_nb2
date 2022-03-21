import aiohttp
from hoshino.sres import Res as R
from hoshino.message import Message

from .._model import BaseInfoChecker, SubscribeRecord
from .._rss import RSS, RSSData


class TwitterChecker(BaseInfoChecker):
    async def notice_format(self, sub: SubscribeRecord, data: RSSData) -> Message:
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

    def form_url(self, distinguisher: str) -> str:
        return RSS.from_route(f"twitter/media/{distinguisher}").url

    def form_remark(self, data: RSSData, distinguisher: str) -> str:
        return f"{data.author}推特"


TwitterChecker(600, "推特", "推特名称")
