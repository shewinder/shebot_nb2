import base64
import pickle
import os
import time
from io import BytesIO
from os import path

import aiohttp
from PIL import Image

from hoshino.sres import Res as R
from hoshino import Service, Bot, Event
from hoshino.typing import T_State
from hoshino.util import DailyNumberLimiter, FreqLimiter
from hoshino.util.sutil  import extract_url_from_event
from .data_source import detect_face, concat, gen_head
from .opencv import add
from .config import plugin_config, Config

conf: Config = plugin_config.config

sv = Service('接头霸王')
_nlt = DailyNumberLimiter(5)
_flt = FreqLimiter(15)

conhead = sv.on_startswith('接头')

@conhead.handle()
async def concat_head(bot: Bot, event: Event, state: T_State):
    uid = event.user_id
    if not _nlt.check(uid):
        await bot.send(event, '今日已经到达上限！')
        return

    if not _flt.check(uid):
        await bot.send(event, '太频繁了，请稍后再来')
        return

    url = extract_url_from_event(event)
    if not url:
        await bot.send(event, '请附带图片!')
        return
    url = url[0]
    await bot.send(event, '请稍等片刻~')

    _nlt.increase(uid)
    _flt.start_cd(uid, 30)

    # download picture and generate base64 str
    # b百度人脸识别api好像无法使用QQ图片服务器的图片，所以使用base64
    async with  aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            cont = await resp.read()
            b64 = (base64.b64encode(cont)).decode()
            img = Image.open(BytesIO(cont))
            img.save(path.join(path.dirname(__file__), 'temp.jpg'))
            picfile = path.join(path.dirname(__file__), 'temp.jpg')
    text = event.get_plaintext().strip('接头')
    if text.startswith('1'):
        mode = 1
    elif text.startswith('2'):
        mode = 2
    else:
        mode = conf.DEFAULT_MODE
    if mode == 1: # 使用百度api接头
        if not conf.CLIENT_ID or not conf.CLIENT_SECRET:
            await bot.send(event, '请配置client_id和client_secret')
            return
        face_data_list = await detect_face(b64)
        if not face_data_list:
            await bot.send(event, 'api未检测到人脸信息')
            return
        face_data_list = await detect_face(b64)
        output = '' ######
        head_gener = gen_head()
        for dat in face_data_list:
            try:
                head = head_gener.__next__() 
            except StopIteration:
                head_gener = gen_head()
                head = head_gener.__next__() 
            output = concat(img, head, dat)
        pic = R.image_from_memory(output)
        await bot.send(event, pic)
    else: # 使用opencv
        picname = time.strftime("%F-%H%M%S") + ".png"
        outpath = path.join(path.dirname(__file__), 'output', picname)
        pic = add(picfile, outpath)
        if add(picfile, outpath):
            await bot.send(event, R.image_from_memory(pic))
        else:
            fail_pic = path.join(path.dirname(__file__), 'data', '接头失败.png')
            await bot.send(event, R.image(fail_pic))