import asyncio
import datetime
from io import BytesIO
from typing import List

import aiohttp
from hoshino import (
    Bot,
    MessageSegment,
    Service,
    event,
    font_dir,
    get_bot_list,
    scheduled_job,
    sucmd,
)
from hoshino.sres import Res as R
from hoshino.typing import GroupMessageEvent
from hoshino.util import aiohttpx
from hoshino.util.message_util import send_group_forward_msg
from hoshino.util.pixiv import PixivIllust
from hoshino.util.sutil import anti_harmony, get_img_from_url, get_service_groups
from hoshino.util.handle_msg import handle_msg
from PIL import Image, ImageFont, ImageDraw

from .config import Config
from .data_source import RankPic, filter_rank, get_rank, get_rankpic
from .score import score_data

help_ = """
启用后会每天固定推送Pixiv日榜
(该功能还在完善中)
""".strip()

conf = Config.get_instance("pixivrank")
sv = Service("Pixiv日榜", enable_on_default=False, help_=help_)
_today_rank: List[int] = []
_today_rank_r18: List[int] = []


def update_last_3_days(pics: List[RankPic]):
    if len(score_data.last_three_days) == 3:
        score_data.last_three_days.pop(0)
    score_data.last_three_days.append([p.pid for p in pics])


async def generate_preview(sv: Service, pics: List[RankPic]) -> Image.Image:
    imgs: List[Image.Image] = []
    for pic in pics:
        try:
            url = pic.url.replace("i.pximg.net", "pixiv.shewinder.win")
            sv.logger.info(f"downloading {url}")
            im = await get_img_from_url(url)
            imgs.append(im)
        except:
            sv.logger.warning(f"download {url} failed")
    if len(imgs) == 0:
        return None

    # Create a new image with the size of the first image.
    width = 1800
    header = 200
    height = 3000 + header
    canvas = Image.new("RGB", (width, height), color=(250, 250, 250))
    font = ImageFont.truetype(font_dir.joinpath("msyh.ttf").as_posix(), 100)
    draw = ImageDraw.Draw(canvas)
    tip = "发送pr<n>获取原图, 例pr3" if sv.name == "Pixiv日榜" else "发送prr<n>获取原图,例prr3"
    w, h = font.getsize(tip)
    draw.text(
        (int((width - w) / 2), (int((header - h) / 2))), tip, fill="black", font=font
    )
    for i, im in enumerate(imgs):
        row, col = divmod(i, 3)
        if im.height > im.width:  # 竖向图
            im = im.resize((600, int(600 / im.width * im.height)))
            margin = int((im.height - 600) / 2)
            im = im.crop(box=(0, margin, im.width, margin + im.width))
        if im.height < im.width:
            im = im.resize((int(600 / im.height * im.width), 600))
            margin = int((im.width - 600) / 2)
            im = im.crop(box=(margin, 0, im.height + margin, im.height))
        canvas.paste(im, (col * 600, row * 600 + header))
    return canvas

async def generate_forward(sv: Service, pics: List[RankPic]):
    msgs = []
    for pic in pics:
        msgs.append(
            MessageSegment.text(
                f"{pic.pid}: {pic.page_count}\n{pic.author}\n{pic.author_id}"
            )
        )
        if pic.page_count == 1:
            try:
                sv.logger.info(f"downloading {pic.url}")
                msgs.append(
                    await R.image_from_url(
                        pic.url.replace("i.pximg.net", "pixiv.shewinder.win"),
                        anti_harmony=True,
                    )
                )
            except:
                pass
        else:
            nest_msgs = []
            if len(pic.urls) > 5:
                pic.urls = pic.urls[0 : 5]
            for url in pic.urls:
                try:
                    sv.logger.info(f"downloading {url}")
                    nest_msgs.append(
                        await R.image_from_url(
                            url.replace("i.pximg.net", "pixiv.shewinder.win"),
                            anti_harmony=True,
                        )
                    )
                except:
                    pass
            msgs.append(nest_msgs)
    return msgs


async def send_rank(sv: Service, pics: List[RankPic]):
    preview = await generate_preview(sv, pics)
    bot: Bot = get_bot_list()[0]
    gids = await get_service_groups(sv_name=sv.name)
    sv.logger.info("sending pixiv rank")

    for gid in gids:
        try:
            preview = anti_harmony(preview)
            await bot.send_group_msg(group_id=gid, message=R.image_from_memory(preview))
            #await send_group_forward_msg(bot, gid, msgs)
            sv.logger.info(f"群{gid} 投递成功！")
        except Exception as e:
            sv.logger.exception(e)
        await asyncio.sleep(120)


@scheduled_job("cron", hour=conf.hour, minute=conf.minute, id="pixiv日榜")
async def pixiv_rank():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    date = f"{yesterday}"
    sv.logger.info("正在获取日榜")
    pics = await get_rank(date)
    sv.logger.info("日榜获取完毕")
    pics = filter_rank(pics)
    update_last_3_days(pics)
    _today_rank.clear()
    _today_rank.extend([pic.pid for pic in pics])
    await send_rank(sv, pics)


detail = sv.on_command("pr")


@detail.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    arg = str(event.get_message())
    try:
        n = int(arg)
    except:
        await bot.send(event, "not a number")
    if n < 1 or n > 15:
        await bot.send(event, "数字超限")
        return
    idx = n - 1

    if len(_today_rank) == 0:
        await bot.send(event, "日榜未更新")
        return
    p = _today_rank[idx]

    # call pid xxx
    await handle_msg(bot, event, f"pid {p}")


sv_r18 = Service("Pixiv日榜R18", enable_on_default=False, visible=False)
detail_r18 = sv_r18.on_command("prr")


@detail_r18.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    arg = str(event.get_message())
    try:
        n = int(arg)
    except:
        await bot.send(event, "not a number")
    if n < 1 or n > 15:
        await bot.send(event, "数字超限")
        return
    idx = n - 1

    if len(_today_rank_r18) == 0:
        await bot.send(event, "日榜未更新")
        return
    p = _today_rank_r18[idx]

    await handle_msg(bot, event, f"pid {p}")


@scheduled_job("cron", hour=conf.hour, minute=conf.minute + 15, id="pixiv日榜r18")
async def pixiv_rank():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    date = f"{yesterday}"
    sv_r18.logger.info("正在下载日榜图片")
    pics = await get_rank(date, "day_r18")
    sv_r18.logger.info("日榜图片下载完成")
    pics = filter_rank(pics)
    score_data.last_three_days[-1].extend(
        [p.pid for p in pics]
    )  # 由于r18榜晚发，此时过去三天已经更新过了
    _today_rank_r18.clear()
    _today_rank_r18.extend([pic.pid for pic in pics])
    await send_rank(sv_r18, pics)


def add_tag_score(tag: str, score: int):
    if tag in score_data.tag_scores:
        score_data.tag_scores[tag] += score
    else:
        score_data.tag_scores[tag] = score


def add_author_score(author_id: str, score: int):
    if author_id in score_data.author_scores:
        score_data.author_scores[author_id] += score
    else:
        score_data.author_scores[author_id] = score


def favor(pic: RankPic):
    for tag in pic.tags:
        add_tag_score(tag, 1)
    add_author_score(str(pic.author_id), 1)


def dislike(pic: RankPic):
    for tag in pic.tags:
        add_tag_score(tag, -1)
    add_author_score(str(pic.author_id), -1)


fav = sucmd("favor")


@fav.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    try:
        int(str(event.get_message()))
    except ValueError:
        await bot.send(event, "请输入正确的Pixiv ID")
        return
    pid = str(event.get_message())
    rank_pic = await get_rankpic(pid)
    favor(rank_pic)
    await bot.send(event, f"更新tag {rank_pic.tags}\n更新作者 {rank_pic.author}")


dis = sucmd("dislike")


@dis.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    try:
        int(str(event.get_message()))
    except ValueError:
        await bot.send(event, "请输入正确的Pixiv ID")
        return
    pid = str(event.get_message())
    rank_pic = await get_rankpic(pid)
    dislike(rank_pic)
    await bot.send(event, f"更新tag {rank_pic.tags}\n更新作者 {rank_pic.author}")


add_tag = sucmd("tag", only_to_me=False)


@add_tag.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    try:
        tag, score = str(event.message).split(" ")
        int(score)
    except:
        tag = str(event.message)
        score = 0  # 默认为0
    add_tag_score(tag, int(score))
    await bot.send(event, f"更新tag {tag}, score {score_data.tag_scores[tag]}")
