from typing import Union
from hoshino import sucmd, Bot, GroupMessageEvent, PrivateMessageEvent
from .._model import Setu
from hoshino.util.pixiv import get_pixiv_illust
from hoshino.util import aiohttpx
from .._tag import tag_data
from .._tag_parser import parser

add_setu = sucmd("/setu add")


@add_setu.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    args = event.message.extract_plain_text().split()
    if len(args) == 3:
        pid, p, r18 = tuple(args)
        if not pid.isdigit() or not p.isdigit():
            await bot.send(event, "pid和p必须是数字")
            return
        pid, p = int(pid), int(p)
        r18 = True if r18 == "1" else False
    elif len(args) == 2:
        pid, p = tuple(args)
        if not pid.isdigit() or not p.isdigit():
            await bot.send(event, "pid和p必须是数字")
            return
        pid, p = int(pid), int(p)
        r18 = False
    elif len(args) == 1:
        pid = args[0]
        if not pid.isdigit():
            await bot.send(event, "pid必须是数字")
            return
        pid = int(pid)
        p = 0
        r18 = False
    else:
        await bot.send(event, "请输入正确的格式 /setu add pid p")
        return

    pid = int(pid)
    p = int(p)
    illust = await get_pixiv_illust(pid)
    setu = Setu()
    setu.pid = pid
    setu.p = p
    setu.uid = illust.user.id
    setu.title = illust.title
    setu.author = illust.user.name
    setu.r18 = r18
    setu.width = illust.width
    setu.height = illust.height
    setu.tags = [tag.name for tag in illust.tags if tag.name and len(tag.name) > 1]
    setu.tags.extend(
        [
            tag.translated_name
            for tag in illust.tags
            if tag.translated_name and len(tag.translated_name) > 1
        ]
    )
    setu.tags = ",".join(setu.tags)
    setu.ext = "jpg"
    setu.upload_date = illust.create_date
    setu.url = illust.urls[p].replace("i.pximg.net", "pixiv.shewinder.win")
    apiurl = "https://api.shewinder.win/setu/insert"
    resp = await aiohttpx.post(apiurl, data=f"[{setu.json()}]")
    if resp.status_code == 200:
        d = resp.json
        rows = d["rows affected"]
        parser.append_dictionary(setu.tags.split(","))
        tag_data.tags.extend(setu.tags.split(","))
        await bot.send(event, f"{rows} rows affected")
    else:
        await bot.send(event, f"添加失败 {resp.status_code}")
