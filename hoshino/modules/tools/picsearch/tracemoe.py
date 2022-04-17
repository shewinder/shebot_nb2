from typing import List, Optional

import aiohttp
from pydantic import BaseModel

class TracemoeResult(BaseModel):
    filename: Optional[str]
    episode: Optional[int]
    similarity: float # 0.xxxx
    anilist_id: Optional[int]
    anime: Optional[str]
    at: Optional[float]
    is_adult: bool
    mal_id: Optional[int]
    season: Optional[str]
    title: Optional[str]
    title_chinese: Optional[str]
    title_english: Optional[str]
    title_native: Optional[str]
    title_romaji: Optional[str]
    tokenthumb: Optional[str]

async def get_tracemoe_results(pic_url, min_simirality):
    """
    min_simirality 0-1
    """
    url = 'https://trace.moe/api/search'
    params = {
        'url' : pic_url
    }
    res_list: List[TracemoeResult] = []
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            try:
                results = await resp.json()
                results = results['docs']
            except:
                return []
            for i in results:
                r = TracemoeResult(**i)
                if r.similarity < min_simirality:
                    continue
                res_list.append(r)
            return res_list

async def tracemoe_format(r: TracemoeResult):
    reply = [
        f'相似度: {round(r.similarity, 3)}',
        f'名称: {r.title_chinese}',
        f'季: {r.season}',
        f'集数: {r.episode}',
        f'秒数: {r.at}',
        f'是否成人: {"是" if r.is_adult else "否"}'
    ]
    return '\n'.join(reply)