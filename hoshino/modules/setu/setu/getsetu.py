from re import I
from typing import List

import aiohttp
import requests
from io import BytesIO
from PIL import Image

from hoshino.log import logger
from .config import plugin_config, Config
from .model import  Setu

conf: Config = plugin_config.config

def get_lolicon_setu(r18: int=0, keyword: str='', num: int=1):
    api = r'https://api.lolicon.app/setu'
    params = {
        'r18': r18,
        'keyword':keyword,
        'num':num,
        'size1200': True
        }
    setu_list=[]
    resp = requests.get(api, params=params, timeout=20)
    if resp.status_code != 200:
        logger.warning('访问lolicon api发生异常')
        return None
    data = resp.json()
    data = data['data']
    for i in data:
        setu = Setu(**i)
        setu_list.append(setu)
    return setu_list

async def download_setu(session: aiohttp.ClientSession, setu: Setu):
    url: str = setu.url
    url = url.replace('https://i.pixiv.cat/', conf.proxy_site)
    try:
        logger.info(f'正在下载{url}')
        async with session.get(url) as resp:
            content = await resp.read()
            logger.info(f'{url}下载完成')
            img = Image.open(BytesIO(content))
            if setu.r18==1:
                img = img.convert('RGB')
                img = anti_harmony(img)

            out = BytesIO()
            img.save(out, format='png')
            setu.picbytes = out.getvalue()
    except Exception as ex:
        print(ex)
        setu.picbytes = None
    return setu

def setu_by_keyword(keyword: str, num: int=1, r18: int=0) -> List[Setu]:
    return get_lolicon_setu(r18=r18, keyword=keyword, num=num) # 暂时摸了

def anti_harmony(img: Image.Image) -> Image.Image:
    #img = img.convert('RGB')
    W, H = img.size[0], img.size[1]
    pos1 = 1,1
    pos2 = W-1,H-1
    img.putpixel(pos1,(255,255,200))
    img.putpixel(pos2,(255,255,200))
    return img


