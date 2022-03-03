import json
import os
from typing import Tuple

from nonebot.adapters.cqhttp.message import MessageSegment

from hoshino import res_dir, userdata_dir
from hoshino.sres import Res as R, ResImg
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
