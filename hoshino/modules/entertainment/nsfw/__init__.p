import random
from loguru import logger

from hoshino import T_State
from hoshino import Service, Bot, Event
from hoshino.util.sutil import extract_url_from_event
from .data_source import detect_img_url

sv = Service('nsfw')

detect = sv.on_command('nsfw', aliases={'鉴黄', '涩图鉴定'}, only_group=False)
@detect.handle()
async def _(bot:Bot, event: Event, state: T_State):
    urls = extract_url_from_event(event)
    if urls:
        state['url'] = urls[0]

@detect.got('url', prompt='请发送图片')
async def _(bot:Bot, event: Event, state: T_State):
    url = extract_url_from_event(event)[0]
    if url:
        state['url'] = url
    rst = await detect_img_url(url)
    reply = [
        f'drawings: {round(float(rst["drawings"]), 3)}',
        f'hentai: {round(float(rst["hentai"]), 3)}',
        f'porn: {round(float(rst["porn"]), 3)}'
    ]
    await detect.send('\n'.join(reply))

sv1 = Service('nsfw-for-fun')
fun = sv1.on_message()
replys = ['还有吗？多来点', '就这？', '多发点，我朋友爱看', '摩多摩多']
#@fun.handle()
async def _(bot:Bot, event: Event):
    urls = extract_url_from_event(event)
    if not urls:
        return
    url = urls[0]
    rst = await detect_img_url(url)
    hentai = rst['hentai']
    porn = rst['porn']
    sv1.logger.info(f'hentai: {hentai}')
    if hentai > 0.5:
        rand = random.random()
        sv1.logger.info(f'nsfw for fun rand {rand}')
        if rand < 0.4:
            await fun.send(random.choice(replys))
    if porn > 0.8:
        rand = random.random()
        if rand < 0.3:
            await fun.send('来点二次元')

