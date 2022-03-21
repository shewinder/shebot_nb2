from hoshino.glob import get_browser
from hoshino.sres import Res as R
from nonebot.adapters.cqhttp.message import Message

from .._config import Config, plugin_config
from .._model import BaseInfoChecker, SubscribeRecord
from .._rss import RSS, RSSData

conf: Config = plugin_config.config


class WeiboChecker(BaseInfoChecker):
    async def notice_format(self, sub: SubscribeRecord, data: RSSData) -> Message:
        browser = await get_browser()
        page = await browser.new_page()
        await page.goto(data.portal)
        articles = page.locator("//article")
        screen_bytes = await articles.first.screenshot()  # 截图
        await page.close()
        return (
            f"{sub.remark}更新了！" + R.image_from_memory(screen_bytes) + f"{data.portal}"
        )

    @classmethod
    async def get_data(self, url: str) -> RSSData:
        rss = RSS(url=url)
        await rss.get()
        return rss.parse_xml()

    def form_url(self, distinguisher: str) -> str:
        return RSS.from_route(f"weibo/user/{distinguisher}").url

    def form_remark(self, data: RSSData, distinguisher: str) -> str:
        return data.channel_title


WeiboChecker(120, "微博", "博主Id")
