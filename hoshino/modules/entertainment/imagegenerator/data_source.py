from typing import Optional

from nonebot.adapters.cqhttp.message import MessageSegment

from hoshino import res_dir
from hoshino.sres import Res as R
from .bieming import biemings
from .config import Config
from hoshino.config import get_plugin_config_by_name

pc: Config = get_plugin_config_by_name('imagegenerator')

plug_resdir = res_dir.joinpath("imagegenerator/image_data")

def get_name_from_bieming(bieming: str) -> Optional[str]:
    for k, v in biemings.items():
        if bieming in v:
            return k
    return None

def choose_image(uid_str: str, bieming: str) -> MessageSegment:
    if bieming == "random":
        pc.user[uid_str] = "random"
        return "随机图片"
    name = get_name_from_bieming(bieming)
    if not name:
        return False
    pc.user[uid_str] = name
    p = plug_resdir.joinpath(f"{name}/{name}.jpg")
    return R.image(p)


def get_user_image(uid: str) -> str:
    # 优先从用户自定义图片中获取，默认值为配置文件中的默认图片
    img_name = pc.user.get(str(uid), pc.initial)
    return img_name
