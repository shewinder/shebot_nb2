import asyncio
import hashlib
from json.decoder import JSONDecodeError

from loguru import logger
import json
import os
import random
import re
from io import BytesIO
from os import path
from typing import List, Union
from pathlib import Path

import aiohttp
from PIL import Image, ImageDraw, ImageFont

from hoshino import Event, Service

async def download_async(url: str, path: Union[str, Path]) -> None:
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            content = await resp.read()
            with open(path, 'wb') as f:
                f.write(content)

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

def save_config(config:dict,path:str, indent=2):
    try:
        with open(path,'w',encoding='utf8') as f:
            json.dump(config, f, ensure_ascii=False, indent=indent)
        return True
    except Exception as ex:
        print(f'exception occured when saving config to {path}')
        raise
        #return False

def load_config(path):
    try:
        with open(path, mode='r', encoding='utf-8') as f:
            config = json.load(f)
            return config
    except JSONDecodeError:
        logger.warning(f'exception occured when loading config, maybe empty json file')
        return {}

async def get_img_from_url(url) -> Image.Image:
    async with  aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            cont = await resp.read()
            img = Image.open(BytesIO(cont))
            return img

def add_text_to_img(img: Image.Image, text:str, textsize:int, font='msyh.ttf', textfill='black', position:tuple=(0,0)):
    """textsize ????????????
    font ???????????????????????????
    textfill ???????????????????????????
    position ???????????????0,0????????????????????????????????????"""
    img_font = ImageFont.truetype(font=font,size=textsize)
    draw = ImageDraw.Draw(img)
    draw.text(xy=position,text=text,font=img_font,fill=textfill)

async def get_service_groups(sv_name):
    """???????????????????????????????????????"""
    svs = Service.get_loaded_services()
    if sv_name not in svs:
        raise ValueError(f'??????????????? {sv_name}')
    enable_groups = await svs[sv_name].get_enable_groups()
    return enable_groups.keys()

def anti_harmony(img: Image.Image) -> Image.Image:
    img = img.copy()
    W, H = img.size[0], img.size[1]
    pos1 = 1,1
    pos2 = W-1,H-1
    img.putpixel(pos1,(255,255,random.randint(0,255)))
    img.putpixel(pos2,(255,255,random.randint(0,255)))
    return img

