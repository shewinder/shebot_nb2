# -*- coding:utf-8 -*-

from pathlib import Path
from PIL import ImageDraw, Image, ImageFont

from hoshino import font_dir
from hoshino.sres import Res as R
from .data_source import get_image_config, get_user_image

def img(msg: str, uid: int):
    img_name, img = get_user_image(str(uid))
    color = get_image_config(img_name, 'color')
    font_size = get_image_config(img_name, 'font_size')
    font_max = get_image_config(img_name, 'font_max')
    image_font_center = (get_image_config(img_name, 'font_center_x'), get_image_config(img_name, 'font_center_y'))
    image_font_sub = get_image_config(img_name, 'font_sub')

    img: Image = img.open()
    draw = ImageDraw.Draw(img)

    font_path = font_dir.joinpath('simhei.ttf')
    ttfront = ImageFont.truetype(font_path.as_posix(), font_size)  # 设置字体暨字号
    font_length = ttfront.getsize(msg)
    #print(font_length)
    while font_length[0]>font_max:
        font_size-=image_font_sub
        ttfront = ImageFont.truetype(font_path.as_posix(), font_size)
        font_length = ttfront.getsize(msg)
    #print(ttfront.getsize("你好"))
    # 自定义打印的文字和文字的位置
    if font_length[0]>5:
        draw.text((image_font_center[0]-font_length[0]/2, image_font_center[1]-font_length[1]/2),
                    msg, fill=color,font=ttfront)
        return R.image_from_memory(img)
