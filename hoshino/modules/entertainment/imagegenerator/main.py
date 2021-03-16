# -*- coding:utf-8 -*-

from PIL import ImageDraw, Image, ImageFont
import os
from os import path
from . import get
from hoshino.sres import Res as R

async def img(bot, ev, msg, uid):

    image_path = path.join(path.dirname(__file__), f'image-generate/image/{uid}.jpg')
    if os.path.exists(image_path):
        os.remove(image_path)
    file = await get.getQqName(uid)
    color = await get.getIni(file,"color")
    ini = str(await get.getIni(file,"name"))
    image_path_new = path.join(path.dirname(__file__), f'image-generate/image_data/{file}/{ini}.jpg')

    img = Image.open(image_path_new)
    draw = ImageDraw.Draw(img)
    font_size=await get.getIni(file,"font_size")
    font_max=await get.getIni(file,"font_max")
    image_font_center=(await get.getIni(file,"font_center_x"),await get.getIni(file,"font_center_y"))
    image_font_sub = await get.getIni(file,"font_sub")
    font_path = path.join(path.dirname(__file__), 'simhei.ttf')
    ttfront = ImageFont.truetype(font_path, font_size)  # 设置字体暨字号
    font_length = ttfront.getsize(msg)
    #print(font_length)
    while font_length[0]>font_max:
        font_size-=image_font_sub
        ttfront = ImageFont.truetype(font_path, font_size)
        font_length = ttfront.getsize(msg)
    #print(ttfront.getsize("你好"))
    # 自定义打印的文字和文字的位置
    if font_length[0]>5:
        draw.text((image_font_center[0]-font_length[0]/2, image_font_center[1]-font_length[1]/2),
                    msg, fill=color,font=ttfront)
        #img.save(image_path)
        #pic_path = path.join(path.dirname(__file__), f'image-generate/image/{uid}.jpg')
        #pic = R.image(pic_path)
        await bot.send(ev, R.image_from_memory(img), at_sender=False)
