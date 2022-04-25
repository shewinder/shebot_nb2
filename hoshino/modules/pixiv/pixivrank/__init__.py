import asyncio
import datetime
from typing import List

from hoshino import Bot, Service, get_bot_list, scheduled_job, sucmd
from hoshino.sres import Res as R
from hoshino.typing import GroupMessageEvent
from hoshino.util.message_util import send_group_forward_msg
from hoshino.util.sutil import get_service_groups
from hoshino import MessageSegment

from .data_source import RankPic, filter_rank, get_rank, get_rankpic
from .score import score_data
from .config import Config
from hoshino.config import get_plugin_config_by_name

help_ = """
启用后会每天固定推送Pixiv日榜
(该功能还在完善中)
""".strip()

conf: Config = get_plugin_config_by_name('pixivrank')
sv = Service("Pixiv日榜", enable_on_default=False, help_=help_)


def update_last_3_days(pics: List[RankPic]):
    if len(score_data.last_three_days) == 3:
        score_data.last_three_days.pop(0)
    score_data.last_three_days.append([p.pid for p in pics])


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

    # 处理发送
    bot: Bot = get_bot_list()[0]
    gids = await get_service_groups(sv_name=sv.name)
    notice = MessageSegment.text("今日Pixiv日榜")
    msgs = []
    for pic in pics:
        msgs.append(
            MessageSegment.text(
                f"{pic.pid}: {pic.page_count}\n{pic.author}\n{pic.author_id}"
            )
        )
        try:
            msgs.append(await R.image_from_url(pic.url.replace('i.pximg.net','pixiv.shewinder.win'), anti_harmony=True))
        except:
            pass # 图片获取失败, skip

    for gid in gids:
        await asyncio.sleep(0.5)
        try:
            await bot.send_group_msg(message=notice, group_id=gid)
            await send_group_forward_msg(bot, gid, msgs)
            sv.logger.info(f"群{gid} 投递成功！")
        except Exception as e:
            sv.logger.exception(e)
            sv.logger.error(type(e))


sv_r18 = Service("Pixiv日榜R18", enable_on_default=False, visible=False)


@scheduled_job("cron", hour=conf.hour, minute=conf.minute+5, id="pixiv日榜r18")
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
    bot: Bot = get_bot_list()[0]
    gids = await get_service_groups(sv_name=sv_r18.name)
    notice = MessageSegment.text("Pixiv R18日榜")
    msgs = []
    for pic in pics:
        msgs.append(
            MessageSegment.text(
                f"{pic.pid}: {pic.page_count}\n{pic.author}\n{pic.author_id}"
            )
        )
        try:
            msgs.append(await R.image_from_url(pic.url.replace('i.pximg.net','pixiv.shewinder.win'), anti_harmony=True))
        except Exception as e:
            pass
        # msgs.append(MessageSegment.image(pic.url))

    for gid in gids:
        try:
            await bot.send_group_msg(message=notice, group_id=gid)
            await send_group_forward_msg(bot, gid, msgs)
            sv_r18.logger.info(f"群{gid} 投递成功！")
        except Exception as e:
            sv_r18.logger.exception(e)
            sv_r18.logger.error(type(e))
        await asyncio.sleep(30)


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
