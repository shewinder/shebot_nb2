from dataclasses import dataclass
from typing import Dict, List

import aiohttp


@dataclass
class RankPic:
    pid: int
    url: str
    tags: List[str]
    score: int
    page_count: int
    author: str
    author_id: int

async def get_rank(date: str, mode: str='day') -> List[RankPic]:
    url = 'https://api.shewinder.win/pixiv/rank'
    params = {
        "date" : date,
        "mode" : mode,
        "num" : 60
    }
    res = []
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                for d in data:
                    if d['type'] != 'illust':
                        continue
                    if d['page_count'] == 1:
                        url = d['meta_single_page']['original_image_url']
                    else:
                        url = d['meta_pages'][0]['image_urls']['original']
                    res.append(RankPic(d['id'], 
                               url.replace('i.pximg.net','pixiv.shewinder.win'), 
                               d['tags'], 0, 
                               d['page_count'],
                               d['user']['name'],
                               d['user']['id'],
                               ))
                return res

def filter_rank(pics: List[RankPic], tag_scores: Dict[str, int]) -> List[RankPic]:
    for pic in pics:
        sum = 0
        for tag in pic.tags:
            if tag['name'] in tag_scores:
                sum += tag_scores[tag['name']]
        pic.score = sum
    pics.sort(key=lambda x: x.score, reverse=True)
    return pics[0:15]

async def get_tags(pid: str) -> List[str]:
    url = 'https://api.shewinder.win/pixiv/illust_detail'
    params = {
        "illust_id" : pid
    }
    res = []
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                #data = data['illust']
                tags = data['tags']
                for tag in tags:
                    res.append(tag['name'])
                return res

if __name__ == '__main__':
    import asyncio
    import datetime
    tag_scores = {
        "原神": 2,
        "genshin": 2, 
        "yuri": 1, 
        "loli": 1, 
        "lolicon": 1, 
        "萝莉": 1, 
        "百合": 1, 
        "公主连接": 1,
        "pcr": 1, 
        "公主链接": 1
    }
    async def test():
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=2)
        date = f'{yesterday}'
        pics = await get_rank(date)
        print(pics[0])
        pics = filter_rank(pics, tag_scores)
        print([pic.url + str(pic.pid) for pic in pics])
        for pic in pics:
            print(pic.url, pic.tags, pic.score)
        tags = await get_tags('82418071')
        print(tags)
    asyncio.run(test())

