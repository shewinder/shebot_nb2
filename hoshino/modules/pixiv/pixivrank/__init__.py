import asyncio
import datetime
import re
from io import BytesIO
from typing import List, Optional, Tuple

import aiohttp
from hoshino import (
    Bot,
    MessageSegment,
    Service,
    font_dir,
    get_bot_list,
    scheduled_job,
    sucmd,
)
from hoshino.log import logger
from hoshino.sres import Res as R
from hoshino.event import GroupMessageEvent
from hoshino.util.sutil import anti_harmony, get_img_from_url, get_service_groups
from hoshino.util.handle_msg import handle_msg
from PIL import Image, ImageFont, ImageDraw

from .config import Config
from .data_source import RankPic, filter_rank, get_rank, get_rankpic
from .score import score_data, save_score_data, load_score_data
from hoshino.util import _strip_cmd

help_ = """
启用后会每天固定推送Pixiv日榜
""".strip()

conf = Config.get_instance("pixivrank")
sv = Service("Pixiv日榜", enable_on_default=False, help_=help_)
sv_r18 = Service("Pixiv日榜R18", enable_on_default=False, visible=False)
_today_rank: List[RankPic] = []
_today_rank_r18: List[RankPic] = []


def get_text_size(font, text):
    """兼容新旧版本Pillow的文本尺寸获取函数"""
    try:
        # Pillow >= 10.0.0
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        # Pillow < 10.0.0
        return font.getsize(text)


def update_last_3_days(pics: List[RankPic]):
    if len(score_data.last_three_days) == 3:
        score_data.last_three_days.pop(0)
    score_data.last_three_days.append([p.pid for p in pics])
    save_score_data()


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
    w, h = get_text_size(font, tip)
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
                pic.urls = pic.urls[0:5]
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


async def send_rank(sv: Service, pics: List[RankPic], gids: List[int]=None):
    preview = await generate_preview(sv, pics)
    bot: Bot = get_bot_list()[0]
    if not gids:
        gids = await get_service_groups(sv_name=sv.name)
    sv.logger.info("sending pixiv rank")

    for gid in gids:
        try:
            preview = anti_harmony(preview)
            await bot.send_group_msg(group_id=gid, message=R.image_from_memory(preview))
            # await send_group_forward_msg(bot, gid, msgs)
            sv.logger.info(f"群{gid} 投递成功！")
        except Exception as e:
            sv.logger.exception(e)
        await asyncio.sleep(120)


detail = sv.on_command("pr", handlers=[_strip_cmd])


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
    await handle_msg(bot, event, f"pid {p.pid}")


detail_r18 = sv_r18.on_command("prr", handlers=[_strip_cmd])


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

    await handle_msg(bot, event, f"pid {p.pid}")


@scheduled_job("cron", hour=conf.hour, minute=conf.minute + 1, id="pixiv日榜")
async def pixiv_rank():
    await send_rank(sv, _today_rank)


@scheduled_job("cron", hour=conf.hour, minute=conf.minute + 5, id="pixiv日榜r18")
async def pixiv_rank():
    await send_rank(sv_r18, _today_rank_r18)


async def update_rank(bot: Bot = None, event: GroupMessageEvent = None):
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    date = f"{yesterday}"
    logger.info("正在下载日榜")
    pics = await get_rank(date)
    logger.info("日榜下载完成")
    pics = filter_rank(pics)
    update_last_3_days(pics)
    _today_rank.clear()
    _today_rank.extend(pics)

    logger.info("正在下载r18日榜")
    pics = await get_rank(date, "day_r18")
    pics = filter_rank(pics)
    logger.info("r18日榜下载完成")
    score_data.last_three_days[-1].extend([p.pid for p in pics])
    _today_rank_r18.clear()
    _today_rank_r18.extend(pics)
    save_score_data()


sucmd("更新日榜").handle()(update_rank)


@sucmd("预览日榜").handle()
async def _(bot: Bot, event: GroupMessageEvent):
    await send_rank(sv, _today_rank, gids=[event.group_id])
    await send_rank(sv_r18, _today_rank_r18, gids=[event.group_id])


scheduled_job("cron", hour=conf.hour, minute=conf.minute, id="pixiv日榜数据更新")(update_rank)


def add_tag_score(tag: str, score: int):
    if tag in score_data.tag_scores:
        score_data.tag_scores[tag] += score
    else:
        score_data.tag_scores[tag] = score
    save_score_data()


def add_author_score(author_id: str, score: int):
    if author_id in score_data.author_scores:
        score_data.author_scores[author_id] += score
    else:
        score_data.author_scores[author_id] = score
    save_score_data()


def favor(pic: RankPic):
    for tag in pic.tags:
        add_tag_score(tag, 1)
    add_author_score(str(pic.author_id), 1)


def dislike(pic: RankPic):
    for tag in pic.tags:
        add_tag_score(tag, -1)
    add_author_score(str(pic.author_id), -1)


async def resolve_rankpic_from_arg(arg: str) -> Tuple[Optional[RankPic], Optional[str]]:
    """
    解析参数为 RankPic 对象
    
    支持三种格式：
    1. 纯数字 PID: "123456"
    2. 日榜索引: "pr1", "pr2", ... (从 _today_rank 获取)
    3. R18日榜索引: "prr1", "prr2", ... (从 _today_rank_r18 获取)
    
    返回: (RankPic对象, 错误消息)
    如果成功，返回 (RankPic, None)
    如果失败，返回 (None, 错误消息)
    """
    arg = arg.strip()
    
    # 检查是否为纯数字 PID
    if arg.isdigit():
        rank_pic = await get_rankpic(arg)
        if rank_pic is None:
            return None, "无法获取该Pixiv ID的作品信息"
        return rank_pic, None
    
    # 检查是否为 pr<n> 格式
    pr_match = re.match(r'^pr(\d+)$', arg, re.IGNORECASE)
    if pr_match:
        try:
            n = int(pr_match.group(1))
            if n < 1 or n > 15:
                return None, "数字超限，请输入1-15之间的数字"
            
            if len(_today_rank) == 0:
                return None, "日榜未更新"
            
            if n > len(_today_rank):
                return None, f"索引超出今日日榜范围（当前共{len(_today_rank)}个作品）"
            
            idx = n - 1
            return _today_rank[idx], None
        except (ValueError, IndexError):
            return None, "索引格式错误"
    
    # 检查是否为 prr<n> 格式
    prr_match = re.match(r'^prr(\d+)$', arg, re.IGNORECASE)
    if prr_match:
        try:
            n = int(prr_match.group(1))
            if n < 1 or n > 15:
                return None, "数字超限，请输入1-15之间的数字"
            
            if len(_today_rank_r18) == 0:
                return None, "R18日榜未更新"
            
            if n > len(_today_rank_r18):
                return None, f"索引超出今日R18日榜范围（当前共{len(_today_rank_r18)}个作品）"
            
            idx = n - 1
            return _today_rank_r18[idx], None
        except (ValueError, IndexError):
            return None, "索引格式错误"
    
    # 都不匹配
    return None, "参数错误：请使用 Pixiv ID 或 pr<n>/prr<n>"


fav = sucmd("favor", handlers=[_strip_cmd])


@fav.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    arg = str(event.get_message()).strip()
    rank_pic, error_msg = await resolve_rankpic_from_arg(arg)
    
    if rank_pic is None:
        await bot.send(event, error_msg or "请输入正确的Pixiv ID或日榜索引")
        return
    
    favor(rank_pic)
    await bot.send(event, f"更新tag {rank_pic.tags}\n更新作者 {rank_pic.author}")


dis = sucmd("dislike", handlers=[_strip_cmd])


@dis.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    arg = str(event.get_message()).strip()
    rank_pic, error_msg = await resolve_rankpic_from_arg(arg)
    
    if rank_pic is None:
        await bot.send(event, error_msg or "请输入正确的Pixiv ID或日榜索引")
        return
    
    dislike(rank_pic)
    await bot.send(event, f"更新tag {rank_pic.tags}\n更新作者 {rank_pic.author}")


add_tag = sucmd("tag", only_to_me=False, handlers=[_strip_cmd])


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
