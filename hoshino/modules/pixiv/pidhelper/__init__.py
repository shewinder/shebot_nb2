from io import BytesIO
from typing import Dict, List

import aiohttp
from hoshino import MessageSegment, Service
from hoshino.log import logger
from hoshino.sres import Res as R
from hoshino.typing import Bot, GroupMessageEvent
from hoshino.util import aiohttpx
from hoshino.util.message_util import send_group_forward_msg
from hoshino.util.sutil import anti_harmony
from PIL import Image

from .._model import PixivIllust
from .ugoira import get_ugoira_gif

help_ = """
[pid90173025] 发送pixiv对应pid的图片，超过10张只发前10张
如果图片是动图会自动转为gif发送
""".strip()

sv = Service("pid搜图", help_=help_)
pid_helper = sv.on_command("pid")


@pid_helper.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    p = str(event.message).strip()
    try:
        int(p)
    except:
        await bot.send(event, 'invalid pid')
        return

    # 获取illust信息
    resp = await aiohttpx.get(
        f"https://api.shewinder.win/pixiv/illust_detail/", params={"illust_id": p}
    )
    illust_json = resp.json
    if illust_json.get("error"):
        await bot.send(event, illust_json["error"]["user_message"])
        return
    illust = PixivIllust(**illust_json)

    # 处理动图
    if illust.type == "ugoira":
        await bot.send(event, "该图片是动图，转为gif发送")
        sv.logger.info('processing gif')
        gif_bytes = await get_ugoira_gif(p)
        sv.logger.info('gif process finished')
        #await bot.send(event, R.image_from_memory(gif_bytes))
        await send_group_forward_msg(bot, event.group_id, [R.image_from_memory(gif_bytes)])
        return

    # 获取普通图片
    await bot.send(event, "正在下载")

    urls = illust.urls
    if len(urls) > 10:
        await bot.send(event, f"该pid包含{len(urls)}张，只发送前10张")
        urls = urls[:10]
    pics = []
    async with aiohttp.ClientSession() as session:
        for url in urls:
            url = url.replace("i.pximg.net", "pixiv.shewinder.win")
            try:
                picbytes = await download_pic(session, url)
                pics.append(picbytes)
            except Exception as e:
                await bot.send(event, f"download {url} failed  {e}")
                logger.exception(e)
                await bot.send(event, f"{url} 下载失败")
                continue
        reply = [
            f"标题：{illust.title}",
            f"作者：{illust.user.name}",
            f"作者id：{illust.user.id}",
        ]
        msgs = [MessageSegment.text("\n".join(reply))]
        for pic in pics:
            msgs.append(R.image_from_memory(pic))
        await send_group_forward_msg(bot, event.group_id, msgs)


async def download_pic(session: aiohttp.ClientSession, url):
    logger.info(f"正在下载{url}")
    async with session.get(url) as resp:
        if resp.status != 200:
            raise Exception(f"{url} 下载失败")
        content = await resp.read()
        logger.info(f"{url}下载完成")
        img = Image.open(BytesIO(content))
        img = img.convert("RGB")
        img = anti_harmony(img)  # 转发消息试试不反和谐
        out = BytesIO()
        img.save(out, format="png")
        return out.getvalue()
