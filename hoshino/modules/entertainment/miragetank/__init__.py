from nonebot.exception import ParserExit
from hoshino.sres import Res as R
from hoshino import Service, Bot, Event
from hoshino.rule import ArgumentParser
from hoshino.typing import T_State
from hoshino.util import DailyNumberLimiter, FreqLimiter
from hoshino.util.sutil  import extract_url_from_event
from .MTCore import gray_car, color_car
from .config import plugin_config, Config

conf: Config = plugin_config.config

sv = Service('幻影坦克')
_nlt = DailyNumberLimiter(5)
_flt = FreqLimiter(5)

parser = ArgumentParser()
parser.add_argument('-c', '--color', action='store_true')
parser.add_argument('-ch', '--chess', action='store_true')

tank = sv.on_shell_command('幻影坦克', parser=parser, only_group=False)

@tank.handle()
async def handle_tank(bot: Bot, event: Event, state: T_State):
    uid = event.user_id
    if not _nlt.check(uid):
        await bot.send(event, '今日已经到达上限！')
        return

    if not _flt.check(uid):
        await bot.send(event, '太频繁了，请稍后再来')
        return

    urls = extract_url_from_event(event)
    if len(urls) >= 2:
        state['white'] = urls[0]
        state['black'] = urls[1]

@tank.got('white', prompt='请发送白底图')
async def handle_white(bot: Bot, event: Event, state: T_State):
    url = extract_url_from_event(event)[0]
    if url:
        state['white'] = url

@tank.got('black', prompt='请发送黑底图')
async def handle_black(bot: Bot, event: Event, state: T_State):
    url = extract_url_from_event(event)[0]
    if url:
        state['black'] = url
    wimg = await R.img_from_url(state['white'])
    wimg = wimg.open()
    bimg = await R.img_from_url(state['black'])
    bimg = bimg.open()

    args = state['args']
    if isinstance(args, ParserExit):
        args.color = False
        args.chess = False
    if args.color:
        img = color_car(wimg, bimg, chess=args.chess)
    else:
        img = gray_car(wimg, bimg, chess=args.chess)
    pic = R.image_from_memory(img)
    await bot.send(event, pic)






