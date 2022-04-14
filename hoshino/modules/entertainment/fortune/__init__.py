from os import path, listdir
from random import choice
from sre_parse import State
from typing import Dict

from PIL import Image
from hoshino import GroupMessageEvent

from hoshino import Bot, Event, res_dir, font_dir
from hoshino.util import DailyNumberLimiter
from hoshino.sres import Res as R
from hoshino.service import Service
from hoshino.util.sutil import load_config
from .data_source import drawing
from .good_luck import GOOD_LUCK
from .config import Config
from hoshino.config import get_plugin_config_by_name
from hoshino.typing import T_State

conf: Config = get_plugin_config_by_name('fortune')

sv = Service('运势')
_lmt = DailyNumberLimiter(1)
_rst = {}

ftn = sv.on_keyword({'抽签', '运势', '占卜', '人品'})

@ftn.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    plug_dir = res_dir.joinpath('fortune')
    uid = str(event.user_id)
    theme = conf.user_theme.get(uid, conf.theme)
    if theme == 'random':
        dirs = [d for d in listdir(plug_dir) if plug_dir.joinpath(d).is_dir()]
        base_dir = plug_dir.joinpath(choice(dirs))
    else:
        base_dir = plug_dir.joinpath(theme)
    img_dir = base_dir.joinpath('img')
    uid = event.user_id
    if not _lmt.check(uid):
        await ftn.finish(f'您今天抽过签了，再给您看一次哦' + _rst.get(uid))
    
    copywriting = load_config(base_dir.joinpath('copywriting.json'))
    copywriting: Dict = choice(copywriting['copywriting'])

    if copywriting.get('type'): # 有对应的角色文案
        luck_type = choice(copywriting['type'])
        good_luck = luck_type['good-luck']
        content = luck_type['content']
        title = GOOD_LUCK[good_luck]
        chara_id = choice(copywriting['charaid'])
        img_name = f'frame_{chara_id}.jpg'
    else:
        title = copywriting.get('title')
        content = copywriting.get('content')
        img_name = choice(listdir(img_dir))
        

    # 添加文字
    img = Image.open(path.join(img_dir, img_name))
    title_font_path = font_dir.joinpath('Mamelon.otf')
    text_font_path = font_dir.joinpath('sakura.ttf')
    img = drawing(img, title, content, str(title_font_path), str(text_font_path))

    pic = R.image_from_memory(img)
    _rst[uid] = pic
    await bot.send(event, pic)
    _lmt.increase(uid)

choose = sv.on_command('choose', aliases={'选签'})

@choose.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    args = str(event.get_message()).strip()
    themes = [d for d in listdir(res_dir.joinpath('fortune')) if res_dir.joinpath('fortune').joinpath(d).is_dir()]
    state['themes'] = themes
    if not args:
        await bot.send(event, f'请发送主题，当前支持的运势主题有：{str(themes)}, random(随机)')
    else:
        state['theme'] = args
        
@choose.got('theme')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    args = state['theme']
    themes = state['themes']
    if args in themes or args == 'random':
        conf.user_theme[str(event.user_id)] = args
        await choose.send(f'已经将抽签切换为{args}')
    else:
        await choose.send(f'{args}不存在')
        






