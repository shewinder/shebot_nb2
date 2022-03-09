from traceback import print_exc
from typing import Dict, List, Optional, Union

import aiohttp
from hoshino.sres import Res as R
from hoshino.util.sutil import get_img_from_url
from pydantic import BaseModel, ValidationError

from .config import Config, plugin_config

conf: Config = plugin_config.config

async def get_saucenao_results(pic_url):
    url = 'https://saucenao.com/search.php'
    params = {
        'db' : 999,
        'output_type' : 2,
        'testmode' : 1,
        'numres' : 20,
        'url' : pic_url,
        'api_key' : conf.soucenao_apikey
    }
    res_list: List[SoucenaoResult] = []
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            try:
                results = await resp.json()
                results = results['results']
            except:
                print_exc()
                return []
            for i in results:
                try:
                    r = SoucenaoResult(**i)
                    if r.header.similarity < 65:
                        continue
                    res_list.append(r)
                except ValidationError:
                    print_exc()
                    pass
            return res_list


class Data(BaseModel):
    creator: Union[List[str], None, str]
    da_id: Optional[int] = None
    ext_urls: Optional[List[str]] = None
    title: Optional[str] = None
    pixiv_id: Optional[int] = None
    member_name: Optional[str] = None
    member_id: Optional[int] = None
    danbooru_id: Optional[int] = None
    yandere_id: Optional[int] = None
    gelbooru_id: Optional[int] = None
    anime_pictures_id: Optional[int] = None
    material: Optional[str] = None
    characters: Optional[str] = None
    source: Optional[str] = None
    eng_name: Optional[str] = None
    jp_name: Optional[str] = None
    md_id: Optional[int] = None
    mu_id: Optional[int] = None
    mal_id: Optional[int] = None
    part: Optional[str] = None
    artist: Optional[str] = None
    author: Optional[str] = None
    type: Optional[str] = None
    bcy_id: Optional[int] = None
    member_link_id: Optional[int] = None
    bcy_type: Optional[str] = None
    author_name: Optional[str] = None
    author_url: Optional[str] = None
    seiga_id: Optional[int] = None
    fa_id: Optional[int] = None
    e621_id: Optional[int] = None
    tweet_id: Optional[int] = None

class Header(BaseModel):
    similarity: float
    thumbnail: str
    index_id: int
    index_name: str
    dupes: int
    hidden: int

class SoucenaoResult(BaseModel):
    header: Header
    data: Data



async def pixiv_format(r: SoucenaoResult):
    img = await get_img_from_url(r.header.thumbnail)
    img = R.image_from_memory(img)
    return  img \
        +f'相似度 {r.header.similarity}\n' \
        + f'标题: {r.data.title}\n' \
        + f'pid: {r.data.pixiv_id}\n' \
        + f'作者: {r.data.member_name}\n' \
        + f'作者id: {r.data.member_id}\n' \
        + f'链接： {r.data.ext_urls[0]}'

async def twitter_format(r: SoucenaoResult):
    img = await get_img_from_url(r.header.thumbnail)
    img = R.image_from_memory(img)
    return  img \
        + f'相似度 {r.header.similarity}\n' \
        + f'tweet_id: {r.data.tweet_id}\n' \
        + f'twitter_user_id: {r.data.twitter_user_id}\n' \
        + f'链接： {r.data.ext_urls[0]}'

async def danbooru_format(r: SoucenaoResult):
    img = await get_img_from_url(r.header.thumbnail)
    img = R.image_from_memory(img)
    return  img \
        + f'相似度 {r.header.similarity}\n' \
        + f'链接: {r.data.ext_urls[0]}\n' \
        + f'source: {r.data.source}'

async def soucenao_format(r: SoucenaoResult):
    if r.data.pixiv_id is not None:
        return await pixiv_format(r)
    elif r.data.tweet_id is not None:
        return await twitter_format(r)
    elif r.data.danbooru_id is not None:
        return await danbooru_format(r)
    else:
        pass
