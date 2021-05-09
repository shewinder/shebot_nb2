import aiohttp

async def detect_img_url(url: str):
    api_url = 'http://api.shewinder.win/nsfw'
    async with aiohttp.ClientSession() as session:
        params = {'imgUrl': url}
        async with session.get(api_url, params=params) as resp:
            if resp.status == 200:
                json_dic = await resp.json()
            else:
                raise ValueError(f'访问api错误，错误码{resp.status}')
    if json_dic['data']['msg'] == 'SUCCESS':
        return list(json_dic['data']['result'].values())[0]

