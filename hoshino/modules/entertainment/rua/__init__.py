from io import BytesIO
from os import path

import requests
from PIL import Image

from hoshino import Service, Bot, Event
from hoshino.typing import T_State
from hoshino.sres import Res as R
from .config import plugin_config
from .data_source import generate_gif

sv = Service('Rua')
data_dir = path.join(path.dirname(__file__), 'data')

async def handle_rua(bot: Bot, event: Event, state: T_State):
    match = state.get('match')
    rua_id = match.group(1)

    url = f'http://q1.qlogo.cn/g?b=qq&nk={rua_id}&s=160'
    resp = requests.get(url)
    resp_cont = resp.content
    avatar = Image.open(BytesIO(resp_cont))
    output = generate_gif(data_dir, avatar)
    await bot.send(event, R.image(output))

sv.on_regex(r'(?:(?:rua)|(?:Rua)|搓)\[CQ:at,qq=(\d+?)\]', handlers=[handle_rua], normal=False)
sv.on_regex(r'\[CQ:at,qq=(.+?)\] (?:(?:rua)|(?:Rua)|搓)', handlers=[handle_rua], normal=False)

