import os
from hoshino.event import MessageEvent
from hoshino import Service, Bot
from hoshino.typing import T_State
from .data_source import choose_image
from . import main
from .data_source import gen_imgs_preview
from hoshino.sres import Res as R

_help = '''
[选图 猫猫] 选择生成表情包所用的底图
[选图列表] 查看能选择的底图列表,<>内的数字为必选数字
[HelloWorld.jpg] 将.jpg前的文字作为内容来生成表情包
'''.strip()
sv = Service('image-generate',  help_=_help)

choose = sv.on_command('choose pic', aliases = {'选图','imgsw','IMGSW'}, only_group=False)
@choose.handle()
async def _(bot: Bot, event: MessageEvent, state: T_State):
    arg = str(event.get_message()).strip()
    if arg:
        state['arg'] = arg
    
@choose.got('arg', prompt='请选择表情模板' + R.image_from_memory(gen_imgs_preview()))
async def switch_img(bot: Bot, event: MessageEvent, state: T_State):
    name = state['arg']
    uid_str = str(event.user_id)
    name = str(event.get_message()).strip()
    pic = choose_image(uid_str, name)
    if pic:
        await bot.send(event, f'表情已更换为{name}' + pic, at_sender=True)
    else:
        await bot.send(event, '不存在的表情')

gen = sv.on_regex('(.{1,15})\.jpg', only_group=False)
@gen.handle()
async def generate_img(bot: Bot, event: MessageEvent, state: T_State):
    m = str(event.get_message())
    if len(m) > 20:
        return
    match = state['match']
    msg = match.group(1)
    uid = event.user_id
    pic = main.img(msg, uid)
    await gen.send(pic)

imgl = sv.on_command('image list', aliases={'选图列表','imgswl','IMGSWL'}, only_group=False)
@imgl.handle()
async def switch_list(bot: Bot, event: MessageEvent):
    await bot.send(event, R.image_from_memory(gen_imgs_preview()))
