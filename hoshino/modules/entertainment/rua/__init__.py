from io import BytesIO
from os import path

import requests
from PIL import Image

from hoshino import Service, Bot, Event
from hoshino.typing import T_State
from hoshino.sres import Res as R
from hoshino.util.sutil import get_img_from_url, extract_url_from_event
from .config import plugin_config
from .data_source import generate_gif

help_ = """
[艾特群员 rua|搓] 发送一张搓群友头像的动图
""".strip()

sv = Service('Rua', help_=help_)
data_dir = path.join(path.dirname(__file__), 'data')

async def handle_rua(bot: Bot, event: Event, state: T_State):
    match = state.get('match')
    rua_id = match.group(1)

    url = f'http://q1.qlogo.cn/g?b=qq&nk={rua_id}&s=160'
    avatar = await get_img_from_url(url)
    output_bytes = generate_gif(data_dir, avatar)
    await bot.send(event, R.image_from_memory(output_bytes))

sv.on_regex(r'(?:(?:rua)|(?:Rua)|搓)\[CQ:at,qq=(\d+?)\]', handlers=[handle_rua], normal=False)
sv.on_regex(r'\[CQ:at,qq=(.+?)\] (?:(?:rua)|(?:Rua)|搓)', handlers=[handle_rua], normal=False)

rua = sv.on_command('搓', aliases={'rua', 'Rua'})
@rua.handle()
async def handle_rua(bot: Bot, event: Event, state: T_State):
    urls = extract_url_from_event(event)
    if not urls:
        return
    url = urls[0]
    img = await get_img_from_url(url)
    output_bytes = generate_gif(data_dir, img, circle=False)
    await bot.send(event, R.image_from_memory(output_bytes))

