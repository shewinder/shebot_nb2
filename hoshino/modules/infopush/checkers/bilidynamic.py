from typing import Dict, List
import requests

import aiohttp
from pydantic import BaseModel, ValidationError

from hoshino.log import logger
from hoshino.sres import Res as R
from .._model import BaseInfoChecker, InfoData, SubscribeRecord, checker
from hoshino.glob import get_browser, Browser

def get_name_from_uid(uid: str) -> str:
    with requests.get(f'https://api.bilibili.com/x/space/acc/info?mid={uid}&jsonp=jsonp') as resp:
        if resp.status_code == 200:
            json_dic = resp.json()
            return json_dic['data']['name']
        else:
            raise ValueError(f'获取用户名失败，status： {resp.status_code}')

class Dynamic(InfoData):
    pass

@checker
class BiliDynamicChecker(BaseInfoChecker):
    seconds: int = 60
    name: str = 'Bilibili动态'
    distinguisher_name: str = "up id"

    @classmethod
    async def notice_format(cls, sub: SubscribeRecord , data: Dynamic):
        browser: Browser = await get_browser()
        ctx = await browser.new_context(
            viewport={"width": 2560, "height": 1080}, device_scale_factor=2
        )
        page = await ctx.new_page()
        await page.goto(data.portal)
        tops = page.locator("//div[@class='first-card-with-title']")
        await tops.wait_for()
        cards = page.locator('//div[@class="card"]')
        cnt = await tops.count()
        index = 1 if cnt == 1 else 0
        card = cards.nth(index)
        screen_bytes = await card.screenshot()  #截图
        await page.close()
        return f'{sub.remark}更新了！' + R.image_from_memory(screen_bytes) + f'{data.portal}'
    
    @classmethod
    async def get_data(cls, url: str) -> Dynamic:

        headers = {
            'Referer': f'https://space.bilibili.com/${url.split("=")[1]}/',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36'
        }
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.get(url=url, 
                                       headers=headers) as resp:
                    if resp.status == 200:
                        json_dic = await resp.json()
                        if 'cards' not in json_dic['data']:
                            return Dynamic()
                            
                        data = json_dic['data']['cards'][0]


                        dyc = Dynamic()
                        dyc.pub_time = str(data['desc']['timestamp'])
                        dyc.portal = f'https://space.bilibili.com/{data["desc"]["uid"]}/dynamic'
                        return dyc
                    else:
                        logger.warning(f'访问{url}失败，status： {resp.status}')
                        return None
            except Exception as e:
                logger.exception(e)
                return None

    @classmethod
    def form_url(cls, dinstinguisher: str) -> str:
        return f'https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history?host_uid={dinstinguisher}'

    @classmethod
    def form_remark(cls, data: Dynamic, distinguisher: str) -> str:
        name = get_name_from_uid(distinguisher)
        return f'{name}B站动态'