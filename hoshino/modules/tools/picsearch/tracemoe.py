import requests
from pydantic import BaseModel, ValidationError

class TracemoeResult(BaseModel):
    filename: str
    episode: int
    similarity: float # 0.xxxx
    anilist_id: int
    anime: str
    at: float
    is_adult: bool
    mal_id: int
    season: str
    title: str
    title_chinese: str
    title_english: str
    title_native: str
    title_romaji: str
    tokenthumb: str

def get_tracemoe_results(pic_url):
    url = 'https://trace.moe/api/search'
    params = {
        'url' : pic_url
    }
    res_list = []
    with requests.get(url,params) as resp:
        try:
            results = resp.json()['docs']
        except:
            return []
        for i in results:
            r = TracemoeResult(**i)
            if r.similarity < 0.5:
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