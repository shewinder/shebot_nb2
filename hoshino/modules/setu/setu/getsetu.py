from io import BytesIO
from typing import List

import aiohttp
import requests
from hoshino.config import get_plugin_config_by_name
from hoshino.log import logger
from hoshino.util.sutil import anti_harmony
from PIL import Image

from .config import Config
from .model import Setu

conf: Config = get_plugin_config_by_name("setu")


def get_lolicon_setu(r18: int = 0, keyword: str = "", num: int = 1):
    api = r"https://api.lolicon.app/setu"
    params = {"r18": r18, "keyword": keyword, "num": num, "size1200": True}
    setu_list = []
    resp = requests.get(api, params=params, timeout=20)
    if resp.status_code != 200:
        logger.warning("访问lolicon api发生异常")
        return None
    data = resp.json()
    data = data["data"]
    for i in data:
        setu = Setu(**i)
        setu_list.append(setu)
    return setu_list


async def download_setu(session: aiohttp.ClientSession, setu: Setu):
    url: str = setu.url
    url = url.replace("https://i.pixiv.cat/", conf.proxy_site)
    try:
        logger.info(f"正在下载{url}")
        async with session.get(url) as resp:
            content = await resp.read()
            logger.info(f"{url}下载完成")
            img = Image.open(BytesIO(content))
            if setu.r18 == 1:
                img = img.convert("RGB")
                img = anti_harmony(img)

            out = BytesIO()
            img.save(out, format="png")
            setu.picbytes = out.getvalue()
    except Exception as ex:
        print(ex)
        setu.picbytes = None
    return setu


def setu_by_keyword(keyword: str, num: int = 1, r18: int = 0) -> List[Setu]:
    return get_lolicon_setu(r18=r18, keyword=keyword, num=num)  # 暂时摸了
