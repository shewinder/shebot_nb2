from typing import List

import aiohttp

async def get_rank(date: str, mode: str='day', num: str=30, keyword: List=[]):
    url = 'https://api.pixivic.com/ranks'
    params = {
        "page" : 1,
        "date" : date,
        "mode" : mode,
        "pageSize" : num
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                data = data['data']
                favor = []
                remain = []
                for d in data:
                    if d['type'] != 'illust':
                        continue
                    tags = str(d['tags'])
                    for k in ['漫画','manga','foodporn','四格', 'furry']:
                        if k in tags:
                            continue
                    if len(favor) < 12: # 偏好先保留8
                        for k in keyword:
                            if k in str(d['tags']):
                                favor.append(d)
                                continue
                    remain.append(d)
                favor.extend(remain)
                res = []
                for d in favor:
                    url = [url['original'].replace('i.pximg.net','i.pixiv.re') for url in d['imageUrls']][0]
                    res.append(url)
                return res

if __name__ == '__main__':
    import asyncio
    import datetime
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    date = f'{yesterday}'
    asyncio.run(get_rank(date, keyword=['原神','genshin','pcr','PCR']))

