from os import path

from nonebot.adapters.cqhttp import GroupMessageEvent

from hoshino import Service, Bot
from hoshino.sres import Res as R
from hoshino.typing import T_State
from . import main
from . import get

sv = Service('image-generate')

choose = sv.on_command('choose pic', aliases = {'选图','imgsw','IMGSW'})
@choose.handle()
async def switch_img(bot: Bot, event: GroupMessageEvent):
    uid = event.user_id
    msg = event.get_message()
    mark = await get.setQqName(uid, msg)
    if mark != None:
        p = path.join(path.dirname(__file__), f'image-generate/image_data/{mark}/{mark}.jpg')
        img = R.image(p)
        await bot.send(event, f'表情已更换为{msg}' + img, at_sender=True)

gen = sv.on_regex('(.{1,15})\.jpg')
@gen.handle()
async def generate_img(bot: Bot, event: GroupMessageEvent, state: T_State):
    m = str(event.get_message())
    if len(m) > 20:
        return
    match = state['match']
    msg = match.group(1)
    uid = event.user_id
    await main.img(bot, event, msg, uid)

help = sv.on_command('img_help', aliases={'表情包帮助','imghelp'})   
@help.handle()
async def imgen_help(bot: Bot, event: GroupMessageEvent):
    msg = '''
[选图 猫猫] 选择生成表情包所用的底图
[选图列表] 查看能选择的底图列表,<>内的数字为必选数字
[HelloWorld.jpg] 将.jpg前的文字作为内容来生成表情包
'''
    await bot.send(event, msg, at_sender=True)

imgl = sv.on_command('image list', aliases={'选图列表','imgswl','IMGSWL'})
@imgl.handle()
async def switch_list(bot: Bot, event: GroupMessageEvent):
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
