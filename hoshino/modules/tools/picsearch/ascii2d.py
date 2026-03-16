from typing import List

from curl_cffi.requests import AsyncSession
from lxml import etree
from lxml.etree import _Element
from pydantic import BaseModel

from hoshino.sres import Res as R
from hoshino.util.sutil import get_img_from_url
from hoshino import MessageSegment


class Ascii2dResult(BaseModel):
    thumb: str
    ext_url: str
    title: str = ""  # 标题（如果有）
    author: str = ""  # 作者（如果有）


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


def _parse_results(html: _Element, base_url: str, max_results: int = 3) -> List[Ascii2dResult]:
    """解析搜索结果（跳过操作按钮）"""
    results: List[Ascii2dResult] = []
    rows: List[_Element] = html.xpath('//div[@class="row item-box"]')
    
    # 跳过第一个（它是操作按钮）
    for row in rows[1:]:
        if len(results) >= max_results:
            break
        
        try:
            thumb = base_url + row.xpath("./div/img")[0].attrib["src"]
            
            # 尝试获取标题和链接
            link_elem = row.xpath(".//h6/a")
            if not link_elem:
                continue
            
            href = link_elem[0].attrib["href"]
            title = link_elem[0].text or ""
            
            # 尝试获取作者信息
            author = ""
            detail_box = row.xpath(".//div[@class='detail-box gray-link']")
            if detail_box:
                links = detail_box[0].xpath(".//a")
                if len(links) >= 2:
                    author = links[1].text or ""
            
            results.append(Ascii2dResult(
                thumb=thumb,
                ext_url=href,
                title=title,
                author=author
            ))
        except IndexError:
            continue
    
    return results


async def get_ascii2d_results(pic_url, color_count: int = 3) -> List[Ascii2dResult]:
    """
    搜索 ascii2d 图片
    
    Args:
        pic_url: 图片 URL
        color_count: 返回的颜色搜索结果数量（默认3个）
    """
    base_url = "https://ascii2d.net"
    res_list: List[Ascii2dResult] = []
    
    # 使用 curl_cffi 模拟 Chrome 浏览器 TLS 指纹
    async with AsyncSession(impersonate="chrome120") as session:
        # 1. 色合搜索 (颜色搜索)
        color_url = base_url + f"/search/url/{pic_url}"
        resp = await session.get(color_url)
        
        if _check_cloudflare(resp.text):
            raise Exception("ascii2d 搜索被 Cloudflare 拦截，请稍后重试")
        
        color_html: _Element = etree.HTML(resp.text)
        color_results = _parse_results(color_html, base_url, max_results=color_count)
        
        if not color_results:
            raise Exception("色合搜索未找到结果")
        
        res_list.extend(color_results)
        
        # 2. 特征搜索 (bovw) - 尝试获取1个
        hash_elem = color_html.xpath('//div[@class="hash"]/text()')
        if hash_elem:
            img_hash = hash_elem[0].strip()
            bovw_url = f"{base_url}/search/bovw/{img_hash}"
            
            try:
                resp = await session.get(bovw_url)
                
                if not _check_cloudflare(resp.text):
                    bovw_html: _Element = etree.HTML(resp.text)
                    bovw_results = _parse_results(bovw_html, base_url, max_results=1)
                    res_list.extend(bovw_results)
            except Exception:
                # 特征搜索失败，忽略
                pass

        return res_list


async def ascii2d_format(data: Ascii2dResult, index: int = 0):
    """格式化单个搜索结果"""
    try:
        img = await get_img_from_url(data.thumb)
        img_seg = R.image_from_memory(img)
    except:
        img_seg = MessageSegment.text("[预览图下载失败]")
    
    # 构建文本
    text_parts = []
    if index > 0:
        text_parts.append(f"{index}.")
    if data.title:
        text_parts.append(f"标题: {data.title}")
    if data.author:
        text_parts.append(f"作者: {data.author}")
    text_parts.append(data.ext_url)
    
    return img_seg + "\n" + "\n".join(text_parts)
