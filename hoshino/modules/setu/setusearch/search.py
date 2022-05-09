from typing import List, Tuple
from hoshino.util import aiohttpx
from .._model import Setu, yande_to_setu, Yande
from urllib.parse import quote

async def search_by_tag(keyword: str, tags: List[str]) -> Tuple[List[Setu], List[str]]:
    apiurl = 'https://api.shewinder.win/setu/search'
    params = {'keyword': keyword, 'tags': ','.join(tags)}
    resp = await aiohttpx.get(apiurl, params=params)
    if resp.status_code != 200:
        raise Exception(f'status {resp.status_code}')
    data = resp.json
    return [Setu(**d) for d in data['data']], data['tag_hit']

async def search_yande(tags: List[str]) -> List[Setu]:
    url = f'https://yande.shewinder.win/post.json?tags={quote("+".join(tags))}+order:score&limit=100'
    resp = await aiohttpx.get(url)
    if resp.status_code != 200:
        raise Exception(f'status {resp.status_code}')
    data = resp.json
    return [yande_to_setu(Yande(**d)) for d in data]

    
