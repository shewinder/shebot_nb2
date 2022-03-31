from typing import Optional

from nonebot.adapters.cqhttp.message import MessageSegment

from hoshino import res_dir, userdata_dir
from hoshino.sres import Res as R
from hoshino.util.sutil import load_config, save_config
from .bieming import biemings
from .config import Config
from hoshino.pluginconfig import get_plugin_config_by_name

pc: Config = get_plugin_config_by_name('imagegenerator')

plug_resdir = res_dir.joinpath("imagegenerator/image_data")

plug_dir = userdata_dir.joinpath("imagegenerator")
if not plug_dir.exists():
    plug_dir.mkdir()

plug_userdata = plug_dir.joinpath("user.json")
if not plug_userdata.exists():
    plug_userdata.touch()


def get_name_from_bieming(bieming: str) -> Optional[str]:
    for k, v in biemings.items():
        if bieming in v:
            return k
    return None


def choose_image(uid_str: str, bieming: str) -> MessageSegment:
    user_data = load_config(plug_userdata)
    if bieming == "random":
        user_data[uid_str] = "random"
        save_config(user_data, plug_userdata)
        return "随机图片"
    name = get_name_from_bieming(bieming)
    if not name:
        return False
    user_data[uid_str] = name
    save_config(user_data, plug_userdata)
    p = plug_resdir.joinpath(f"{name}/{name}.jpg")
    return R.image(p)


def get_user_image(uid: str) -> str:
    conf = load_config(plug_userdata)
    # 优先从用户自定义图片中获取，默认值为配置文件中的默认图片
    img_name = conf.get(uid, pc.initial)
    return img_name
