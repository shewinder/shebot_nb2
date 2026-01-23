from typing import List, Optional, Tuple, Type
from io import BytesIO
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import os
import json
import unicodedata
import time
from nonebot.adapters.onebot.v11 import Event, GroupMessageEvent, PrivateMessageEvent
from nonebot.typing import T_State
import pytz
import base64
import zhconv
import nonebot

from nonebot.utils import run_sync
from nonebot.adapters.onebot.v11 import Bot, MessageSegment
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.plugin import CommandGroup, on_command
from nonebot.rule import Rule, to_me

from hoshino import font_dir

DEFAULTFONT = ImageFont.truetype(os.path.join(font_dir, 'msyh.ttf'), size=48)

class FreqLimiter:
    def __init__(self, default_cd_seconds):
        self.next_time = defaultdict(float)
        self.default_cd = default_cd_seconds

    def check(self, key) -> bool:
        return bool(time.time() >= self.next_time[key])

    def start_cd(self, key, cd_time=0):
        self.next_time[key] = time.time(
        ) + cd_time if cd_time > 0 else self.default_cd


class DailyNumberLimiter:
    tz = pytz.timezone('Asia/Shanghai')

    def __init__(self, max_num):
        self.today = -1
        self.count = defaultdict(int)
        self.max = max_num

    def check(self, key) -> bool:
        now = datetime.now(self.tz)
        day = (now - timedelta(hours=5)).day
        if day != self.today:
            self.today = day
            self.count.clear()
        return bool(self.count[key] < self.max)

    def get_num(self, key):
        return self.count[key]

    def increase(self, key, num=1):
        self.count[key] += num

    def reset(self, key):
        self.count[key] = 0


def get_bot_list() -> List[Bot]:
    return list(nonebot.get_bots().values())


def sucmd(name: str, only_to_me: bool = False, aliases: Optional[set] = None, **kwargs) -> Type[Matcher]:
    kwargs['aliases'] = aliases
    kwargs['permission'] = SUPERUSER
    kwargs['rule'] = to_me() if only_to_me else Rule()
    return on_command(name, **kwargs)


def sucmds(name: str, only_to_me: bool = False, **kwargs) -> CommandGroup:
    kwargs['permission'] = SUPERUSER
    kwargs['rule'] = to_me() if only_to_me else Rule()
    return CommandGroup(name, **kwargs)


def get_text_size(text: str, font: ImageFont.ImageFont = DEFAULTFONT, padding: Tuple[int, int, int, int] = (20, 20, 20, 20), spacing: int = 5) -> tuple:
    '''
    返回文本转图片的图片大小

    *`text`：用来转图的文本
    *`font`：一个`ImageFont`实例
    *`padding`：一个四元`int`元组，分别是左、右、上、下的留白大小
    *`spacing`: 文本行间距
    '''
    with Image.new('RGBA', (1, 1), (255, 255, 255, 255)) as base:
        dr = ImageDraw.ImageDraw(base)
    # Pillow 10.0.0+ 使用 textbbox 替代已移除的 textsize
    bbox = dr.textbbox((0, 0), text, font=font, spacing=spacing)
    width = bbox[2] - bbox[0]  # right - left
    height = bbox[3] - bbox[1]  # bottom - top
    return width+padding[0]+padding[1], height+padding[2]+padding[3]


def text2pic(text: str, font: ImageFont.ImageFont = DEFAULTFONT, padding: Tuple[int, int, int, int] = (20, 20, 20, 20), spacing: int = 5) -> Image.Image:
    '''
    返回一个文本转化后的`Image`实例

    *`text`：用来转图的文本
    *`font`：一个`ImageFont`实例
    *`padding`：一个四元`int`元组，分别是左、右、上、下的留白大小
    *`spacing`: 文本行间距
    '''
    size = get_text_size(text, font, padding, spacing)
    base = Image.new('RGBA', size, (255, 255, 255, 255))
    dr = ImageDraw.ImageDraw(base)
    dr.text((padding[0], padding[2]), text, font=font,
            fill='#000000', spacing=spacing)
    return base


def pic2b64(pic: Image.Image) -> str:
    buf = BytesIO()
    pic.save(buf, format='PNG')
    base64_str = base64.b64encode(
        buf.getvalue()).decode()  # , encoding='utf8')
    return 'base64://' + base64_str


def text2Seg(text: str, font: ImageFont.ImageFont = DEFAULTFONT, padding: Tuple[int, int, int, int] = (20, 20, 20, 20), spacing: int = 5) -> MessageSegment:
    return MessageSegment.image(pic2b64(text2pic(text, font, padding, spacing)))


def concat_pic(pics, border=5):
    num = len(pics)
    w, h = pics[0].size
    des = Image.new('RGBA', (w, num * h + (num-1) * border),
                    (255, 255, 255, 255))
    for i, pic in enumerate(pics):
        des.paste(pic, (0, i * (h + border)), pic)
    return des


def normalize_str(string: str) -> str:
    """
    规范化unicode字符串 并 转为小写 并 转为简体
    """
    string = unicodedata.normalize('NFKC', string)
    string = string.lower()
    string = zhconv.convert(string, 'zh-hans')
    return string


async def parse_qq(bot: Bot, event: Event, state: T_State):
    ids = []
    if isinstance(event, GroupMessageEvent):
        for m in event.get_message():
            if m.type == 'at' and m.data['qq'] != 'all':
                ids.append(int(m.data['qq']))
        for m in event.get_plaintext().split():
            if m.isdigit():
                ids.append(int(m))
    elif isinstance(event, PrivateMessageEvent):
        for m in event.get_plaintext().split():
            if m.isdigit():
                ids.append(int(m))
    if ids:
        state['ids'] = ids.copy()


def get_event_image(event: Event) -> List[str]:
    msg=event.get_message()
    imglist=[
        s.data['file']
        for s in msg
        if s.type == 'image' and 'file' in s.data
    ]
    return imglist

def get_event_imageurl(event: Event) -> List[str]:
    msg=event.get_message()
    imglist=[
        s.data['url']
        for s in msg
        if s.type == 'image' and 'url' in s.data
    ]
    return imglist

async def _strip_cmd(bot: "Bot", event: "Event", state: T_State):
    message = event.get_message()
    segment = message.pop(0)
    segment_text = str(segment).lstrip()
    new_message = message.__class__(
        segment_text[len(state["_prefix"]["raw_command"]) :].lstrip()
    )  # type: ignore
    for new_segment in reversed(new_message):
        message.insert(0, new_segment)