from hoshino.sres import Res as R
from nonebot.adapters.cqhttp.message import Message

from .._config import Config, plugin_config
from .._model import BaseInfoChecker, InfoData, SubscribeRecord
from .._rss import RSS

from playwright.async_api import async_playwright

conf: Config = plugin_config.config

class Weibo(InfoData):
    channel_title: str
    title: str
    desc: str

class WeiboChecker(BaseInfoChecker):
    #async def notice_format(self, sub: SubscribeRecord, data: Weibo):
    #    return Message(f'{sub.remark}更新了\n{data.title}\n{data.portal}')
    async def notice_format(self, sub: SubscribeRecord, data: Weibo) -> Message:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(data.portal)
            articles = page.locator("//article")
            screen_bytes = await articles.first.screenshot()  #截图
            await browser.close()
        return f'{sub.remark}更新了！' + R.image_from_memory(screen_bytes) + f'{data.portal}'

    @classmethod
    async def get_data(self, url: str) -> Weibo:
        rss = RSS(url=url)
        await rss.get()
        data = rss.parse_xml()
        wb = Weibo(pub_time=data['pubDate'], portal=data['link'])
        wb.title = data['title']
        wb.desc = data['desc']
        wb.channel_title = data['channel_title']
        return wb

WeiboChecker(10)
