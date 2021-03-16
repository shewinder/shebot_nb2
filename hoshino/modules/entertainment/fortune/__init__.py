from os import path, listdir
from random import choice

from PIL import Image
from nonebot.adapters.cqhttp import GroupMessageEvent

from hoshino import Bot, Event
from hoshino.util import DailyNumberLimiter
from hoshino.sres import Res as R
from hoshino.service import Service
from hoshino.util.sutil import load_config
from .data_source import drawing
from .good_luck import GOOD_LUCK
from .config import plugin_config, Config

sv = Service('运势')
_lmt = DailyNumberLimiter(1)
_rst = {}
conf: Config = plugin_config.config

ftn = sv.on_keyword({'抽签', '运势', '占卜', '人品'})

@ftn.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    global _divines
    uid = event.user_id
    if not _lmt.check(uid):
        await ftn.finish(f'您今天抽过签了，再给您看一次哦' + _rst.get(uid))
    
    base_dir = path.join(path.dirname(__file__), 'data', conf.theme)
    img_dir = path.join(base_dir, 'img')
    copywriting = load_config(path.join(base_dir, 'copywriting.json'))
    copywriting = choice(copywriting['copywriting'])

    if copywriting.get('type'): # 有对应的角色文案
        luck_type = choice(copywriting['type'])
        good_luck = luck_type['good-luck']
        content = luck_type['content']
        title = GOOD_LUCK[good_luck]
        chara_id = choice(copywriting['charaid'])
        img_name = f'frame_{chara_id}.jpg'
    else:
        good_luck = copywriting.get('good-luck')
        content = copywriting.get('content')
        title = GOOD_LUCK[good_luck]
        img_name = choice(listdir(img_dir))
        

    # 添加文字
    img = Image.open(path.join(img_dir, img_name))
    title_font_path = path.join(path.dirname(__file__),  'font', 'Mamelon.otf')
    text_font_path = path.join(path.dirname(__file__),  'font', 'sakura.ttf')
    img = drawing(img, title, content, title_font_path, text_font_path)

    pic = R.image_from_memory(img)
    _rst[uid] = pic
    await bot.send(event, pic)
    _lmt.increase(uid)

choose = sv.on_command('choose', aliases={'选签'})

@choose.handle()
async def _(bot: Bot, event: Event):
    args = str(event.get_message()).strip()
    if args:
        plugin_config.set('theme', args)
        await choose.send(f'已经将抽签切换为{args}')






