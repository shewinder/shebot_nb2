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
from PIL import Image, ImageDraw, ImageFont

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

def add_text_to_img(img: Image.Image, text:str, textsize:int, font='msyh.ttf', textfill='black', position:tuple=(0,0)):
    #textsize 文字大小
    #font 字体，默认微软雅黑
    #textfill 文字颜色，默认黑色
    #position 文字偏移（0,0）位置，图片左上角为起点
    img_font = ImageFont.truetype(font=font,size=textsize)
    draw = ImageDraw.Draw(img)
    draw.text(xy=position,text=text,font=img_font,fill=textfill)


