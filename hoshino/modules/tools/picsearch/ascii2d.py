from typing import Dict, List, Union

import aiohttp
from lxml import etree
from pydantic import BaseModel

from hoshino.sres import Res as R
from hoshino.util.sutil import get_img_from_url

async def get_ascii2d_results(pic_url):
    base_url = 'https://ascii2d.net'
    res_list: List[Ascii2dResult] = []
    async with aiohttp.ClientSession() as session:
        url = base_url + f'/search/url/{pic_url}'
        headers = {"User-Agent": "PostmanRuntime/7.29.0"}
        async with session.get(url, headers=headers) as resp:
            t = await resp.text()
            html = etree.HTML(t)
            rows = html.xpath('//div[@class="row item-box"]')
            for row in rows:
                try:
                    thumb = base_url + row.xpath('./div/img')[0].attrib['src']
                    href = row.xpath('.//h6/a')[0].attrib['href']
                    res_list.append(Ascii2dResult(thumb=thumb, ext_url=href))
                except IndexError:
                    continue
            return res_list



class Ascii2dResult(BaseModel):
    thumb: str
    ext_url: str

async def ascii2d_format(data: Ascii2dResult):
    img = await get_img_from_url(data.thumb)
    img = R.image_from_memory(img)
    return  img + data.ext_url