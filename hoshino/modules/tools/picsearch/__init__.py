from nonebot.adapters.cqhttp.message import Message

from hoshino.typing import T_State
from hoshino import Service, Bot, Event
from hoshino.sres import Res as R
from hoshino.util.sutil import extract_url_from_event
from .soucenao import *
from .tracemoe import *

sv = Service('搜图找番')

search_pic = sv.on_command('search pic', aliases={'搜图', '找图'}, only_group=False)

@search_pic.handle()
async def _(bot: "Bot", event: "Event", state: T_State):
    urls = extract_url_from_event(event)
    if urls:
        state['url'] = urls[0]

@search_pic.got('url', prompt='请发送图片')
async def _(bot: "Bot", event: "Event", state: T_State):
    if state['url'] == '取消':
        await search_pic.finish('本次搜图已经取消')
    urls = extract_url_from_event(event)
    if not urls:
        await search_pic.reject(event,'未检测到图片，请重新发送或者发送“取消”结束')

    url = urls[0] 
    await bot.send(event, '正在搜索，请稍后~')
    results = await get_saucenao_results(url)
    results = results[0:3] if len(results) >= 3 else results
    if results:
        reply = '以下结果来自souceNao\n'
        for r in results:
            if isinstance(r.data, PixivData):
                # pixiv结果
                reply += await pixiv_format(r)
            elif isinstance(r.data, TwitterData):
                reply += await twitter_format(r)
            elif isinstance(r.data, DanbooruData):
                reply += await danbooru_format(r)
        await search_pic.finish(reply)
    # 自动转为搜索番剧模式
    results = await get_tracemoe_results(url, 0.9)
    if results:
        reply = '以下结果来自tracemoe\n\n'
        results = results[0:3] if len(results) >= 3 else results
        for r in results:
            reply += await tracemoe_format(r) + '\n\n'
        await search_pic.finish(reply)
    # 都没有结果
    await bot.send(event, '没找到结果哦')

search_anime = sv.on_command('search anime', aliases={'搜番', '找番'}, only_group= False)

@search_anime.handle()
async def _(bot: "Bot", event: "Event", state: T_State):
    urls = extract_url_from_event(event)
    if urls:
        state['url'] = urls[0]

@search_anime.got('url', prompt='请发送截图, 注意裁剪截图黑边以获得更高准确率')
async def _(bot: "Bot", event: "Event", state: T_State):
    if state['url'] == '取消':
        await search_anime.finish('本次搜番已经取消')
    urls = extract_url_from_event(event)
    if not urls:
        await search_anime.reject(event,'未检测到图片，请重新发送或者发送“取消”结束')

    url = urls[0]
    await bot.send(event, '正在搜索，请稍后~')
    results = await get_tracemoe_results(url, 0.8)
    if results:
        reply = '以下结果来自tracemoe\n\n'
        results = results[0:3] if len(results) >= 3 else results
        for r in results:
            reply += await tracemoe_format(r) + '\n\n'
        await bot.send(event, reply)
    else:
        await bot.send(event, '没有找到呢~')
