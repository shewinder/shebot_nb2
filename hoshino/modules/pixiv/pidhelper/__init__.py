from io import BytesIO
from typing import Dict, List

import requests
import aiohttp
from PIL import Image

from hoshino import Service
from hoshino.log import logger
from hoshino.typing import Bot, MessageEvent
from hoshino.sres import Res as R
from hoshino.util import FreqLimiter

help_ ="""
[pid90173025] 发送pixiv对应pid的图片，超过10张只发前10张
""".strip()

_lmt = FreqLimiter(60)

sv = Service('pid搜图', help_=help_)
pid = sv.on_command('pid')
@pid.handle()
async def _(bot: Bot, event: MessageEvent):
    if not _lmt.check(event.user_id):
        return
    p = str(event.message).strip()
    url = f'https://api.shewinder.win/pixiv/illust_detail'
    async with aiohttp.ClientSession() as session:
        param = {'illust_id': p}
        resp = await session.get(url, params=param)
        if resp.status != 200:
            await pid.finish(f'访问失败')
        data: Dict = await resp.json()
        if data.get('error'):
            await pid.finish(data['error']['user_message'])
        data = data['illust']
        urls: List[str] = []
        if data['page_count'] == 1:
            urls = [data['meta_single_page']['original_image_url']]
        else:
            urls = [d['image_urls']['original'] for d in data['meta_pages']]
        if len(urls) > 10:
            await bot.send(event, f'该pid包含{len(urls)}张，只发送前10张')
            urls = urls[:10]
        async with aiohttp.ClientSession() as session:
            for url in urls:
                url = url.replace('i.pximg.net','pixiv.shewinder.win')
                try:
                    picbytes = await download_pic(session, url)
                except Exception as e:
                    await bot.send(event, f'download {url} failed  {e}')
                    logger.exception(e)
                    break
                await bot.send(event, R.image_from_memory(picbytes))
        _lmt.start_cd(event.user_id)

async def download_pic(session: aiohttp.ClientSession, url):
    logger.info(f'正在下载{url}')
    async with session.get(url) as resp:
        content = await resp.read()
        logger.info(f'{url}下载完成')
        img = Image.open(BytesIO(content))
        img = img.convert('RGB')
        img = anti_harmony(img)
        out = BytesIO()
        img.save(out, format='png')
        return out.getvalue()

def anti_harmony(img: Image.Image) -> Image.Image:
    #img = img.convert('RGB')
    W, H = img.size[0], img.size[1]
    pos1 = 1,1
    pos2 = W-1,H-1
    img.putpixel(pos1,(255,255,200))
    img.putpixel(pos2,(255,255,200))
    return img


########################################################################################################################
#@dataclass
#class PixivIllust:
#    create_at: str
#    title: str
#    page_count: int
#    author: str
#    tags: list[str]
#    
#detail = sv.on_command('pid detail', aliases=('pid详情', 'pid详细'))
#async def _(bot: Bot, event: MessageEvent):
#    p = str(event.get_message())
#    if not p.isdigit():
#        return
#    url = 'http://43.134.194.249:9500/pixiv/illust_detail'
#    params = {
#        "illust_id" : pid
#    }
#    res = []
#    async with aiohttp.ClientSession() as session:
#        async with session.get(url, params=params) as resp:
#            if resp.status == 200:
#                data = await resp.json()
#                data = data['illust']
#                tags = data['tags']

    