import asyncio
import os
import time
from typing import List

import aiohttp
import requests
from io import BytesIO
from PIL import Image
from peewee import SQL, fn

from hoshino.log import logger
from hoshino.util import aiohttpx
from .config import plugin_config, Config
from .data import Setu

conf: Config = plugin_config.config

def get_setu(r18: int, keyword: str, num: int):
    api = r'https://api.lolicon.app/setu'
    params = {
        'apikey': conf.apikey,
        'r18': r18,
        'keyword':keyword,
        'num':num,
        'size1200': True
        }
    setu_list=[]
    try:
        resp = requests.get(api, params=params, timeout=20)
        if resp.status_code != 200:
            logger.warning('访问lolicon api发生异常')
            return None
        data = resp.json()
        for i in data['data']:
            setu = Setu(pid=i['pid'],
                        author=i['author'],
                        title=i['title'],
                        url=i['url'],
                        r18=i['r18'],
                        tags=i['tags'])
            try:
                setu.save(force_insert=True)
                logger.info(f'保存{setu.title}到数据库')
            except Exception as e:
                print(e)
            setu_list.append(setu)
        return setu_list
    except Exception as ex:
        print(ex)
        return None

async def download_one(session: aiohttp.ClientSession, setu: Setu, save_dir, setus: List[Setu]):
    url: str = setu.url
    r18: int = setu.r18
    file = os.path.join(save_dir, url.split('/')[-1])
    if os.path.exists(file):
        print(f'本地已有{setu.title}缓存')
        return
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        logger.info(f'正在下载{url}')
        async with session.get(url) as resp:
            content = await resp.read()
            logger.info(f'{url}下载完成')
            with open(file, 'wb') as f:
                if r18 == 0:
                    f.write(content)
                    f.close()
                elif r18==1:
                    img = Image.open(BytesIO(content))
                    img = img.convert('RGB')
                    #img = img.transpose(Image.ROTATE_90)
                    img = anti_harmony(img)
                    out = BytesIO()
                    img.save(out,format='JPEG')
                    f.write(out.getvalue())
                    f.close()
                setus.append(setu)
    except Exception as ex:
        print(ex)

def get_final_setu(save_dir, num: int=1, r18: int=2, keyword: str=''):
    _pics = []
    setus = get_setu(r18, keyword, num)
    async def gather():
        try:
            async with aiohttp.ClientSession() as session:
                tasks = []
                for setu in setus:
                    task = asyncio.create_task(download_one(session, setu, save_dir, _pics))
                    tasks.append(task)
                await asyncio.gather(*tasks)
        except Exception as e:
            logger.exception(e)
    asyncio.run(gather())
    return _pics
 
def search_in_database(keyword: str, num: int, r18: int):
    if r18 == 2:
        sql = SQL('tags like ? or title like ?', params=[f'%{keyword}%', f'%{keyword}%'])
    else:
        sql = SQL('(tags like ? or title like ?) and r18=?', params=[f'%{keyword}%',f'%{keyword}%',r18])
    logger.info(f'searching {keyword} in database')
    try:
        t1 = time.time()
        setus = Setu.select().where(sql).order_by(fn.Random()).limit(num)
        if not setus:
            setus = Setu.select().where(SQL('author like ? and r18=?', params=[f'%{keyword}%',r18])).order_by(fn.Random()).limit(num)
        t2 = time.time()
        logger.info(f'查询到{len(setus)}条结果,用时{t2-t1}s')
        return setus
    except Exception as e:
        logger.exception(e)
        return None

def anti_harmony(img: Image.Image) -> Image.Image:
    #img = img.convert('RGB')
    W, H = img.size[0], img.size[1]
    pos1 = 1,1
    pos2 = W-1,H-1
    img.putpixel(pos1,(255,255,200))
    img.putpixel(pos2,(255,255,200))
    return img


