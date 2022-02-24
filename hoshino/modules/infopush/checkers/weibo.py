from hoshino.glob import get_browser
from hoshino.sres import Res as R
from nonebot.adapters.cqhttp.message import Message

from .._config import Config, plugin_config
from .._model import BaseInfoChecker, InfoData, SubscribeRecord
from .._rss import RSS

conf: Config = plugin_config.config

class Weibo(InfoData):
    channel_title: str
    title: str
    desc: str

class WeiboChecker(BaseInfoChecker):
    async def notice_format(self, sub: SubscribeRecord, data: Weibo) -> Message:
        browser = await get_browser()
        page = await browser.new_page()
        await page.goto(data.portal)
        articles = page.locator("//article")
        screen_bytes = await articles.first.screenshot()  #截图
        await page.close()
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

    def form_url(self, distinguisher: str) -> str:
        return RSS(f'weibo/user/{distinguisher}').url
    
    def form_remark(self, data: Weibo, distinguisher: str) -> str:
        return data.channel_title

WeiboChecker(120, '微博', '博主Id')
