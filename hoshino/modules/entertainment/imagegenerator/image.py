import json
import math
import os
import random
from dataclasses import dataclass
from typing import List

from hoshino import font_dir, res_dir, userdata_dir
from hoshino.sres import Res as R
from nonebot.adapters.cqhttp.message import MessageSegment
from PIL import Image, ImageDraw, ImageFont

from .bieming import biemings
from .config import Config
from hoshino.pluginconfig import get_plugin_config_by_name

pc: Config = get_plugin_config_by_name("imagegenerator")

plug_resdir = res_dir.joinpath("imagegenerator/image_data")

plug_dir = userdata_dir.joinpath("imagegenerator")
if not plug_dir.exists():
    plug_dir.mkdir()

plug_userdata = plug_dir.joinpath("user.json")
if not plug_userdata.exists():
    plug_userdata.touch()


@dataclass
class ImageConfig:
    name: str
    font_max: int
    font_size: int
    font_center_x: int
    font_center_y: int
    color: str
    font_sub: int


def get_image_config(img_name: str) -> ImageConfig:
    p = plug_resdir.joinpath(f"{img_name}/config.ini")
    with open(p, "r", encoding="utf-8") as f:
        ini = f.read()
    dic = json.loads(ini)
    return ImageConfig(**dic)


def draw(msg: str, img_name: str) -> MessageSegment:
    if img_name == "random":
        img_name = random.choice(os.listdir(plug_resdir))
    cfg = get_image_config(img_name)
    color = cfg.color
    font_size = cfg.font_size
    font_max = cfg.font_max
    image_font_center = cfg.font_center_x, cfg.font_center_y
    image_font_sub = cfg.font_sub
    img = R.img(plug_resdir.joinpath(f"{img_name}/{img_name}.jpg")).open()
    draw = ImageDraw.Draw(img)

    font_path = font_dir.joinpath("simhei.ttf")
    ttfront = ImageFont.truetype(font_path.as_posix(), font_size)  # 设置字体暨字号
    font_length = ttfront.getsize(msg)

    while font_length[0] > font_max:
        font_size -= image_font_sub
        ttfront = ImageFont.truetype(font_path.as_posix(), font_size)
        font_length = ttfront.getsize(msg)

    # 自定义打印的文字和文字的位置
    if font_length[0] > 5:
        draw.text(
            (
                image_font_center[0] - font_length[0] / 2,
                image_font_center[1] - font_length[1] / 2,
            ),
            msg,
            fill=color,
            font=ttfront,
        )
        return R.image_from_memory(img)


def gen_imgs_preview() -> Image.Image:
    """
    Generates a preview image of the given images.
    :param imgs: List of images to be used in the preview.
    :return: Image object of the preview.
    """
    img_dir = res_dir.joinpath("imagegenerator/image_data")
    imgs: List[Image.Image] = []
    files = []
    for dir in os.listdir(img_dir):
        for file in os.listdir(img_dir.joinpath(dir)):
            if file.endswith(".jpg"):
                imgs.append(Image.open(img_dir.joinpath(dir, file)))
                files.append(file.split(".")[0])

    files = [biemings[file] for file in files]

    if len(imgs) == 0:
        return None

    # Create a new image with the size of the first image.
    row_cnt = 5
    col_sep = 20
    row_sep = 40
    isize = 200
    height = math.ceil(len(imgs) / 5) * (isize + row_sep)
    preview = Image.new("RGB", (1080, height), color=(250, 250, 250))
    font = ImageFont.truetype(font_dir.joinpath("sakura.ttf").as_posix(), 35)
    for i, img in enumerate(imgs):
        r, c = divmod(i, row_cnt)
        img = imgs[r * row_cnt + c]
        img = img.resize((isize, isize))
        draw = ImageDraw.Draw(preview)
        preview.paste(img, (c * isize + c * col_sep, r * isize + r * row_sep))
        w, h = font.getsize(files[i][0])
        draw.text(
            (c * (isize + col_sep) + (isize - w) / 2, isize + r * (isize + row_sep)),
            files[i][0],
            fill="black",
            font=font,
        )
    return preview
