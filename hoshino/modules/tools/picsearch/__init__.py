from nonebot.adapters.cqhttp.message import Message

from hoshino.typing import T_State
from hoshino import Service, Bot, Event
from .data_source import saucenao_api,tracemoe_api
from hoshino.sres import Res as R
from hoshino.util.sutil import extract_url_from_event

sv = Service('搜图找番')

search_pic = sv.on_command('search pic', aliases={'搜图', '找图'})

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
    results = saucenao_api(url)
    for res in results:
        if res.similarity < 50: #相似度小于50直接返回
            await bot.send(event, '没有找到符合的图片')
            return
        image = await R.img_from_url(res.thumbnail)
        image = image.cqcode
        await bot.send(event, Message(f'相似度:{res.similarity}\n标题:{res.title}\n{image}pid:{res.pid}\n画师:{res.author}'))
        await bot.send(event, f'{res.url}',at_sender=False)


search_anime = sv.on_command('search anime', aliases={'搜番', '找番'})

@search_anime.handle()
async def _(bot: "Bot", event: "Event", state: T_State):
    urls = extract_url_from_event(event)
    if urls:
        state['url'] = urls[0]

@search_anime.got('url', prompt='请发送图片')
async def _(bot: "Bot", event: "Event", state: T_State):
    if state['url'] == '取消':
        await search_anime.finish('本次搜番已经取消')
    urls = extract_url_from_event(event)
    if not urls:
        await search_anime.reject(event,'未检测到图片，请重新发送或者发送“取消”结束')

    url = urls[0]
    await bot.send(event, '正在搜索，请稍后~')
    ani = tracemoe_api(url)
    if ani:
        is_adult = '是' if ani.is_adult else '否'
        reply = f'相似度:{round(ani.similarity,2)}\n动漫名:{ani.anime}\n季度:{ani.season}\n集数:{ani.episode}\n秒数:{ani.at}\n是否成人动漫:{is_adult}'
        await bot.send(event,reply,at_sender=False)








        

        
