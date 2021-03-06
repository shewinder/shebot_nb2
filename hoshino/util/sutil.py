import asyncio
import hashlib
import json
import os
import random
import re
from io import BytesIO
from os import path
from typing import List, Union

import aiohttp
import filetype
import nonebot
from PIL import Image

from hoshino import Event

async def download_async(url: str, save_path: str, save_name: str, auto_extension=False) -> None:
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            content = await resp.read()
            if auto_extension: #没有指定后缀，自动识别后缀名
                try:
                    extension = filetype.guess_mime(content).split('/')[1]
                except:
                    raise ValueError('不是有效文件类型')
                abs_path = path.join(save_path, f'{save_name}.{extension}')
            else:
                abs_path = path.join(save_path, save_name)
            with open(abs_path, 'wb') as f:
                f.write(content)
                return abs_path

def get_random_file(path) -> str:
    files = os.listdir(path)
    rfile = random.choice(files)
    return rfile

def get_md5(val: Union[bytes, str]) -> str:
    if isinstance(val, str):
        val = val.encode('utf-8')
    m = hashlib.md5()
    m.update(val)
    return m.hexdigest()

async def broadcast(msg,groups=None,sv_name=None):
    bot = nonebot.get_bot()
    #当groups指定时，在groups中广播；当groups未指定，但sv_name指定，将在开启该服务的群广播
    svs = Service.get_loaded_services()
    if not groups and sv_name not in svs:
        raise ValueError(f'不存在服务 {sv_name}')
    if sv_name:
        enable_groups = await svs[sv_name].get_enable_groups()
        send_groups = enable_groups.keys() if not groups else groups
    else:
        send_groups = groups
    for gid in send_groups:
        try:
            await bot.send_group_msg(group_id=gid,message=msg)
            logger.info(f'群{gid}投递消息成功')
            await asyncio.sleep(0.5)
        except ActionFailed as e:
            logger.error(f'在群{gid}投递消息失败,  retcode={e.retcode}')
        except Exception as e:
            logger.exception(e)

def extract_url_from_event(event: Event) -> List[str]:
    urls = re.findall(r'http.*?term=\d', str(event.message))
    return urls

def save_config(config:dict,path:str):
    try:
        with open(path,'w',encoding='utf8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as ex:
        print(f'exception occured when saving config to {path}')
        return False

def load_config(path):
    try:
        with open(path, mode='r', encoding='utf-8') as f:
            config = json.load(f)
            return config
    except Exception as ex:
        print(f'exception occured when loading config in {path}  {ex}')
        return {}

async def get_img_from_url(url) -> Image.Image:
    async with  aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            cont = await resp.read()
            img = Image.open(BytesIO(cont))
            return img

