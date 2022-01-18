from typing import Dict, List, Union

import aiohttp
from pydantic import BaseModel, ValidationError

from hoshino.sres import Res as R
from hoshino.util.sutil import get_img_from_url
from .config import plugin_config, Config

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
                return []
            for i in results:
                try:
                    r = SoucenaoResult(**i)
                    if r.header.similarity < 70:
                        continue
                    res_list.append(r)
                except ValidationError:
                    pass
            return res_list

class ResultHeader(BaseModel):
    similarity: float
    thumbnail: str
    index_id: int
    index_name: str
    dupes: int

class PixivData(BaseModel):
    ext_urls: List[str]
    title: str
    pixiv_id: int
    member_name: str
    member_id: int

class TwitterData(BaseModel):
    ext_urls: List[str]
    created_at: str
    tweet_id: str
    twitter_user_id: str
    twitter_user_handle: str

class DanbooruData(BaseModel):
    ext_urls: List[str]
    danbooru_id: int
    yandere_id: int
    gelbooru_id: int
    creator: str
    material: str
    characters: str
    source: str

class SoucenaoResult(BaseModel):
    header: ResultHeader
    data: Union[PixivData, TwitterData, DanbooruData]

async def pixiv_format(r: SoucenaoResult):
    img = await get_img_from_url(r.header.thumbnail)
    img = R.image_from_memory(img)
    return  img \
        +f'相似度 {r.header.similarity}\n' \
        + f'标题: {r.data.title}\n' \
        + f'pid: {r.data.pixiv_id}\n' \
        + f'作者: {r.data.member_name}\n' \
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