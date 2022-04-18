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
        browser = await get_browser()
        ctx = await browser.new_context(
            viewport={"width": 2560, "height": 1080}, device_scale_factor=2
        )
        page = await ctx.new_page()
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

    @classmethod
    def form_url(cls, distinguisher: str) -> str:
        return RSS.from_route(f"weibo/user/{distinguisher}").url

    @classmethod
    def form_remark(cls, data: RSSData, distinguisher: str) -> str:
        return data.channel_title
