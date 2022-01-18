from os import path, listdir
from random import choice, randrange

from PIL import Image, ImageDraw
from hoshino.typing import T_State
from hoshino.event import GroupMessageEvent

from hoshino import Service, Bot
from hoshino.sres import Res as R
from hoshino.util.sutil import get_img_from_url

help_ ="""
[艾特群员 爬] 发送一张让群友爬的图
[艾特群员 丢] 发送一张丢群友的图
""".strip()
sv = Service('爬', help_=help_)

async def creep(bot: "Bot", event: GroupMessageEvent,  state: T_State):
    creep_id = int(state['match'].group(1))
    url = f'http://q1.qlogo.cn/g?b=qq&nk={creep_id}&s=160'
    avatar = await get_img_from_url(url)
    avatar = get_circle_avatar(avatar, 100)
    # 随机获取一张爬图
    im2 = R.get_random_img('creepthrow').open()
    im2 = im2.resize((500, 500))
    im2.paste(avatar, (0, 400, 100, 500), avatar)  
    await bot.send(event, R.image_from_memory(im2))

sv.on_regex('爬\[cq:at,qq=(\d+?)\]').handle()(creep) # hoshino on_regex会把大写字符转小写
sv.on_regex('\[cq:at,qq=(.+?)\] 爬').handle()(creep)

async def throw(bot: "Bot", event: GroupMessageEvent, state: T_State):
    throw_id = int(state['match'].group(1))
    url = f'http://q1.qlogo.cn/g?b=qq&nk={throw_id}&s=160'
    avatar = await get_img_from_url(url)
    avatar = get_circle_avatar(avatar.convert('RGBA'), 139)
    rotate_angle = randrange(0, 360)
    avatar = avatar.rotate(rotate_angle, resample=Image.BILINEAR)
    _center_pos = (17, 180)
    img = Image.open(path.join(R.base_dir, 'creepthrow/throw.jpg'))
    img.paste(avatar, _center_pos, mask=avatar.split()[3])
    await bot.send(event, R.image_from_memory(img))
    
sv.on_regex('丢\[cq:at,qq=(\d+?)\]').handle()(throw)
sv.on_regex('\[cq:at,qq=(.+?)\] 丢').handle()(throw)



def get_circle_avatar(avatar, size):
    #avatar.thumbnail((size, size))  
    avatar = avatar.resize((size, size))
    scale = 5
    mask = Image.new('L', (size*scale, size*scale), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size * scale, size * scale), fill=255)
    mask = mask.resize((size, size), Image.ANTIALIAS)
    ret_img = avatar.copy()
    ret_img.putalpha(mask)
    return ret_img
