from typing import List

from curl_cffi.requests import AsyncSession
from lxml import etree
from lxml.etree import _Element
from pydantic import BaseModel

from hoshino.sres import Res as R
from hoshino.util.sutil import get_img_from_url
from hoshino import MessageSegment
from hoshino.log import logger


class Ascii2dResult(BaseModel):
    thumb: str
    ext_url: str


def _check_cloudflare(text: str) -> bool:
    """检查是否被 Cloudflare 拦截"""
    return any(x in text for x in [
        "Attention Required!",
        "cf-wrapper",
        "Just a moment...",
        "challenge-error-text",
        "Enable JavaScript and cookies to continue",
        "_cf_chl_opt"
    ])


def _parse_results(html: _Element, base_url: str) -> List[Ascii2dResult]:
    """解析搜索结果，跳过第一个（操作按钮）"""
    results: List[Ascii2dResult] = []
    rows: List[_Element] = html.xpath('//div[@class="row item-box"]')
    
    # 跳过第一个（它是操作按钮：色合検索/特徴検索/詳細登録）
    for row in rows[1:]:
        try:
            thumb = base_url + row.xpath("./div/img")[0].attrib["src"]
            href = row.xpath(".//h6/a")[0].attrib["href"]
            results.append(Ascii2dResult(thumb=thumb, ext_url=href))
        except IndexError:
            continue
    
    return results


async def get_ascii2d_results(pic_url) -> List[Ascii2dResult]:
    base_url = "https://ascii2d.net"
    res_list: List[Ascii2dResult] = []
    
    # 使用 curl_cffi 模拟 Chrome 浏览器 TLS 指纹
    async with AsyncSession(impersonate="chrome120") as session:
        # 1. 色合搜索 (颜色搜索)
        color_url = base_url + f"/search/url/{pic_url}"
        
        resp = await session.get(color_url)
        
        # 检查是否被 Cloudflare 拦截
        if _check_cloudflare(resp.text):
            raise Exception("ascii2d 搜索被 Cloudflare 拦截，请稍后重试")
        
        color_html: _Element = etree.HTML(resp.text)
        color_results = _parse_results(color_html, base_url)
        
        # 取色合搜索的第一个结果
        if color_results:
            res_list.append(color_results[0])
        
        # 2. 特征搜索 (bovw)
        # 从色合搜索结果页面获取特征搜索链接
        bovw_links = color_html.xpath("/html/body/div/div/div[1]/div[1]/div[4]/a[2]/@href")
        if not bovw_links:
            bovw_links = color_html.xpath('//a[contains(@href,"/search/bovw/")]/@href')
        
        if bovw_links:
            bovw_url = base_url + bovw_links[0]
            try:
                resp = await session.get(bovw_url)
                
                # 检查是否被 Cloudflare 拦截
                if not _check_cloudflare(resp.text):
                    bovw_html: _Element = etree.HTML(resp.text)
                    bovw_results = _parse_results(bovw_html, base_url)
                    
                    # 取特征搜索的第一个结果
                    if bovw_results:
                        res_list.append(bovw_results[0])
            except Exception as e:
                logger.error(f"特征搜索失败: {e}")
                # 特征搜索失败，忽略错误，至少返回色合搜索结果
        
        if not res_list:
            raise Exception("未找到搜索结果")

        return res_list


async def ascii2d_format(data: Ascii2dResult):
    try:
        img = await get_img_from_url(data.thumb)
        img = R.image_from_memory(img)
    except:
        img = MessageSegment.text("预览图下载失败")
    return img + data.ext_url
