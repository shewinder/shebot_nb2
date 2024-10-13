from typing import Dict, List, Union

import aiohttp
from lxml import etree
from lxml.etree import _Element
from pydantic import BaseModel

from hoshino.sres import Res as R
from hoshino.util.sutil import get_img_from_url
from hoshino import MessageSegment

class Ascii2dResult(BaseModel):
    thumb: str
    ext_url: str

async def get_ascii2d_results(pic_url) -> List[Ascii2dResult]:
    base_url = "https://ascii2d.net"
    res_list: List[Ascii2dResult] = []
    async with aiohttp.ClientSession() as session:
        # first search by color
        color_url = base_url + f"/search/url/{pic_url}"
        headers = {"User-Agent": "PostmanRuntime/7.29.0"}
        async with session.get(color_url, headers=headers) as resp:
            t = await resp.text()
            color_html: _Element = etree.HTML(t)
            rows: List[_Element] = color_html.xpath('//div[@class="row item-box"]')
            for row in rows:
                try:
                    thumb = base_url + row.xpath("./div/img")[0].attrib["src"]
                    href = row.xpath(".//h6/a")[0].attrib["href"]
                    res_list.append(Ascii2dResult(thumb=thumb, ext_url=href))
                    break
                except IndexError:
                    continue
        # by trait
        bovw_url = (
            base_url
            + color_html.xpath("/html/body/div/div/div[1]/div[1]/div[4]/a[2]/@href")[0]
        )
        async with session.get(bovw_url, headers=headers) as resp:
            t = await resp.text()
            bovw_html: _Element = etree.HTML(t)
            rows: List[_Element] = bovw_html.xpath('//div[@class="row item-box"]')
            for row in rows:
                try:
                    thumb = base_url + row.xpath("./div/img")[0].attrib["src"]
                    href = row.xpath(".//h6/a")[0].attrib["href"]
                    res_list.append(Ascii2dResult(thumb=thumb, ext_url=href))
                    break
                except IndexError:
                    continue        

        return res_list

async def ascii2d_format(data: Ascii2dResult):
    try:
        img = await get_img_from_url(data.thumb)
        img = R.image_from_memory(img)
    except:
        img = MessageSegment.text("预览图下载失败")
    return img + data.ext_url
