from io import BytesIO
from typing import Dict, List

import aiohttp
from PIL import Image

from hoshino import Service, MessageSegment
from hoshino.log import logger
from hoshino.typing import Bot, GroupMessageEvent
from hoshino.sres import Res as R
from hoshino.util.message_util import send_group_forward_msg
from hoshino.util.sutil import anti_harmony
from .._model import Illust

help_ ="""
[pid90173025] 发送pixiv对应pid的图片，超过10张只发前10张
""".strip()

sv = Service('pid搜图', help_=help_)
pid = sv.on_command('pid')
@pid.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    p = str(event.message).strip()
    await bot.send(event, '正在下载')
    url = f'https://api.shewinder.win/pixiv/illust_detail'
    async with aiohttp.ClientSession() as session:
        param = {'illust_id': p}
        resp = await session.get(url, params=param)
        if resp.status != 200:
            await pid.finish(f'访问失败')
        data: Dict = await resp.json()
        if data.get('error'):
            await pid.finish(data['error']['user_message'])
        illust = Illust(**data)
        urls: List[str] = []
        if data['page_count'] == 1:
            urls = [data['meta_single_page']['original_image_url']]
        else:
            urls = [d['image_urls']['original'] for d in data['meta_pages']]
        if len(urls) > 10:
            await bot.send(event, f'该pid包含{len(urls)}张，只发送前10张')
            urls = urls[:10]
        pics = []
        async with aiohttp.ClientSession() as session:
            for url in urls:
                url = url.replace('i.pximg.net','pixiv.shewinder.win')
                try:
                    picbytes = await download_pic(session, url)
                    pics.append(picbytes)
                except Exception as e:
                    await bot.send(event, f'download {url} failed  {e}')
                    logger.exception(e)
                    await bot.send(event, f'{url} 下载失败')
                    continue
            reply = [
                f'标题：{illust.title}',
                f'作者：{illust.user.name}',
                f'作者id：{illust.user.id}',
            ]
            msgs = [MessageSegment.text('\n'.join(reply))]
            for pic in pics:
                msgs.append(R.image_from_memory(pic))
            await send_group_forward_msg(bot, event.group_id, msgs)

async def download_pic(session: aiohttp.ClientSession, url):
    logger.info(f'正在下载{url}')
    async with session.get(url) as resp:
        if resp.status != 200:
            raise Exception(f'{url} 下载失败')
        content = await resp.read()
        logger.info(f'{url}下载完成')
        img = Image.open(BytesIO(content))
        img = img.convert('RGB')
        img = anti_harmony(img) # 转发消息试试不反和谐
        out = BytesIO()
        img.save(out, format='png')
        return out.getvalue()

    