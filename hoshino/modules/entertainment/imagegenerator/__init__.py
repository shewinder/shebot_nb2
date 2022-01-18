from hoshino.event import MessageEvent
from hoshino import Service, Bot
from hoshino.typing import T_State
from .data_source import choose_image
from . import main

_help = '''
[选图 猫猫] 选择生成表情包所用的底图
[选图列表] 查看能选择的底图列表,<>内的数字为必选数字
[HelloWorld.jpg] 将.jpg前的文字作为内容来生成表情包
'''.strip()
sv = Service('image-generate',  help_=_help)

choose = sv.on_command('choose pic', aliases = {'选图','imgsw','IMGSW'}, only_group=False)
@choose.handle()
async def switch_img(bot: Bot, event: MessageEvent):
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
    msg = '''
狗妈<1~3>
熊猫<1~3>
粽子<1~2>
阿夸
臭鼬
好学
黑手
逗乐了
奥利给
kora
珂学家
财布
守夜冠军
恶臭
我爱你
peko
星姐
爱丽丝
猫猫
猪
猫猫猫
gvc
猫
ksm
栞栞
'''
    await bot.send(event, msg, at_sender=True)
