import json
import math
import os
from typing import Optional, Tuple

from nonebot.adapters.cqhttp.message import MessageSegment

from hoshino import res_dir, userdata_dir, font_dir
from hoshino.sres import Res as R
from hoshino.util.sutil import load_config, save_config
from .name import names
from .config import plugin_config, Config

pc: Config = plugin_config.config

plug_res = res_dir.joinpath('imagegenerator')
image_data = plug_res.joinpath('image_data')
plug_data = userdata_dir.joinpath('imagegenerator')
if not plug_data.exists():
    plug_data.mkdir()
user_image_data = plug_data.joinpath('user.json')
if not user_image_data.exists():
    user_image_data.touch()

def get_name_from_bieming(bieming: str):
    for k, v in names.items():
        if  bieming in v:
            return k
    return False

def choose_image(uid_str: str, bieming: str) -> MessageSegment:
    user_data = load_config(user_image_data)
    name = get_name_from_bieming(bieming)
    if not name:
        return False
    user_data[uid_str] = name
    save_config(user_data, user_image_data)
    p = image_data.joinpath(f'{name}/{name}.jpg')
    return R.image(p)

def get_user_image(uid: str) -> Tuple:
    conf = load_config(user_image_data)
    # 优先从用户自定义图片中获取，默认值为配置文件中的默认图片
    img_name = conf.get(uid, pc.initial)
    p = image_data.joinpath(f'{img_name}/{img_name}.jpg')
    return img_name, R.img(p)

def get_image_config(img_name: str, item: str):
    p = image_data.joinpath(f'{img_name}/config.ini')
    with open(p, "r",encoding="utf-8") as f:
        ini = f.read()
    dic =  json.loads(ini)
    return dic[item]


from typing import List
from PIL import Image, ImageDraw, ImageFont
import os

def gen_imgs_preview() -> Image.Image:
    """
    Generates a preview image of the given images.
    :param imgs: List of images to be used in the preview.
    :return: Image object of the preview.
    """
    img_dir = res_dir.joinpath('imagegenerator/image_data')
    imgs: List[Image.Image] = []
    files = []
    for dir in os.listdir(img_dir):
        for file in os.listdir(img_dir.joinpath(dir)):
            if file.endswith('.jpg'):
                imgs.append(Image.open(img_dir.joinpath(dir, file)))
                files.append(file.split('.')[0])

    files = [names[file] for file in files]

    if len(imgs) == 0:
        return None

    # Create a new image with the size of the first image.
    row_cnt = 5
    col_sep = 20
    row_sep = 40
    isize = 200
    height = math.ceil(len(imgs) / 5) * (isize + row_sep)
    preview = Image.new('RGB', (1080, height), color=(250, 250, 250))
    font = ImageFont.truetype(font_dir.joinpath('sakura.ttf').as_posix(), 35)
    for i, img in enumerate(imgs):
        r, c = divmod(i, row_cnt)
        img = imgs[r * row_cnt + c]
        img = img.resize((isize, isize))
        draw = ImageDraw.Draw(preview)
        preview.paste(img, (c * isize + c * col_sep, r * isize + r * row_sep))
        w, h = font.getsize(files[i][0])
        draw.text((c * (isize + col_sep) + (isize-w)/2, isize + r * (isize + row_sep)), files[i][0], fill='black', font=font)
    return preview

