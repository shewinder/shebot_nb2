import aiohttp
from hoshino.glob import get_browser
from hoshino.sres import Res as R
from hoshino import Message
from .._config import Config
from .._model import BaseInfoChecker, SubscribeRecord, checker
from .._rss import RSS, RSSData

conf: Config.get_instance("infopush")


@checker
class WeiboChecker(BaseInfoChecker):
    seconds: int = 120
    name: str = "微博"
    distinguisher_name: str = "博主Id"

    @classmethod
    async def notice_format(self, sub: SubscribeRecord, data: RSSData) -> Message:
        params = {"url": data.portal}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.shewinder.win/screenshot/weibo", params=params
            ) as resp:
                img = await resp.read()
        return f"{sub.remark}更新" + R.image_from_memory(img) + data.portal

    @classmethod
    async def get_data(cls, url: str) -> RSSData:
        rss = RSS(url=url)
        await rss.get()
        return rss.parse_xml()

    @classmethod
    def form_url(cls, distinguisher: str) -> str:
        return RSS.from_route(f"weibo/user/{distinguisher}").url

    @classmethod
    def form_remark(cls, data: RSSData, distinguisher: str) -> str:
        return data.channel_title
