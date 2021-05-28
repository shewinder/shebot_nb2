from typing import Dict, List, Union

import requests
from pydantic import BaseModel, ValidationError

from hoshino.sres import Res as R
from .config import plugin_config, Config

conf: Config = plugin_config.config

def get_saucenao_results(pic_url):
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
    with requests.get(url, params) as resp:
        try:
            results = resp.json()['results']
        except:
            return []
        for i in results:
            try:
                r = SoucenaoResult(**i)
                if r.header.similarity < 50:
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

class SoucenaoResult(BaseModel):
    header: ResultHeader
    data: Union[PixivData, TwitterData]

async def pixiv_format(r: SoucenaoResult):
    img = await R.img_from_url(r.header.thumbnail)
    img = img.cqcode
    return r.header.similarity \
        + img \
        + f'标题: {r.data.title}\n' \
        + f'pid: {r.data.pixiv_id}\n' \
        + f'作者: {r.data.member_name}\n' \
        + f'链接： {r.data.ext_urls[0]}'

async def twitter_format(r: SoucenaoResult):
    img = await R.img_from_url(r.header.thumbnail)
    img = img.cqcode
    return r.header.similarity \
        + img \
        + f'用户id: {r.data.member_id}\n' \
        + f'用户名: {r.data.member_name}\n' \
        + f'链接： {r.data.ext_urls[0]}'