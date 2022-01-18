from io import BytesIO

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
        await pid.finish('该功能占用资源极大，请勿频繁使用')
    p = str(event.get_message())
    if not p.isdigit():
        return
    url = f'https://pixiv.re/{p}.jpg'
    resp = requests.head(url)
    urls = []
    if resp.status_code == 200:
        urls.append(url)
    if resp.status_code == 404:
        cnt = 1
        while True:
            url = f'https://pixiv.re/{p}-{cnt}.jpg'
            resp = requests.head(url)
            if resp.status_code != 200:
                break
            cnt += 1
            urls.append(url)
    if not urls:
        await pid.finish(event, f'未查询到该pid信息')
    if len(urls) > 10:
        urls = urls[0:10]
        await bot.send('该pid包含图片超过10张，只发送前10张')
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                picbytes = await download_pic(session, url)
            except Exception as e:
                await bot.send(event, f'download failed  {e}')
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
        

    