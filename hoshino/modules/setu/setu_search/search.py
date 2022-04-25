from typing import List, Tuple
from hoshino.util import aiohttpx
from .model import Setu

async def search_by_tag(keyword: str, tags: List[str]) -> Tuple[List[Setu], List[str]]:
    apiurl = 'https://api.shewinder.win/setu/search'
    params = {'keyword': keyword, 'tags': ','.join(tags)}
    resp = await aiohttpx.get(apiurl, params=params)
    if resp.status_code != 200:
        raise Exception(f'status {resp.status_code}')
    data = resp.json
    return [Setu(**d) for d in data['data']], data['tag_hit']