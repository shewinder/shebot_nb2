import asyncio
import base64
import datetime
import os
import re
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import aiohttp
from hoshino import (
    Bot,
    Message,
    MessageSegment,
    Service,
    font_dir,
    get_bot_list,
    hsn_config,
    scheduled_job,
    sucmd,
)
from hoshino.log import logger
from hoshino.sres import Res as R
from hoshino.event import GroupMessageEvent
from hoshino.util.sutil import anti_harmony, get_img_from_url, get_service_groups
from hoshino.util.handle_msg import handle_msg
from PIL import Image, ImageFont, ImageDraw

from hoshino.modules.aichat.aichat.session import Session
from hoshino.modules.aichat.aichat.api import api_manager
from hoshino.modules.aichat.aichat.persona import persona_manager

from .config import Config
from .data_source import RankPic, filter_rank, filter_rank_ai, get_rank, get_rankpic
from .score import score_data, save_score_data, load_score_data
from hoshino.util import _strip_cmd

help_ = """
启用后会每天固定推送Pixiv日榜
""".strip()

conf = Config.get_instance("pixivrank")
sv = Service("Pixiv日榜", enable_on_default=False, help_=help_)
sv_r18 = Service("Pixiv日榜R18", enable_on_default=False, visible=False)

# 原始榜单（未筛选）
_raw_rank: List[RankPic] = []
_raw_rank_r18: List[RankPic] = []

# 各群筛选后的榜单
_group_ranks: Dict[int, List[RankPic]] = {}
_group_ranks_r18: Dict[int, List[RankPic]] = {}


async def _download_image_to_base64(image_url: str) -> Optional[str]:
    """下载图片并转为 base64 data URL"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    return None
                image_data = await resp.read()
                if not image_data:
                    return None
                content_type = resp.content_type or ""
                ext = "png"
                if content_type.startswith("image/"):
                    ext = content_type.split("/")[1].split(";")[0].strip()
                    if ext == "jpeg":
                        ext = "jpg"
                else:
                    if "." in image_url:
                        url_part = image_url.split("?")[0]
                        url_ext = os.path.splitext(url_part)[1].lower()
                        if url_ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                            ext = url_ext.lstrip(".")
                base64_data = base64.b64encode(image_data).decode("utf-8")
                return f"data:image/{ext};base64,{base64_data}"
    except Exception:
        return None


async def _implicit_preference_update(
    bot: Bot, event: GroupMessageEvent, pic: RankPic, is_r18: bool
):
    """后台任务：隐式调用 aichat 更新用户画像"""
    try:
        user_id = event.user_id
        group_id = event.group_id

        api_config = api_manager.get_api_config()
        if not api_config or not api_config.get("api_key"):
            return

        # 创建独立 Session（不干扰用户的正常对话历史）
        session_id = f"private_{user_id}_pixivrank"
        persona = persona_manager.get_persona(user_id, group_id)
        session = Session(session_id, persona)

        # 激活 image_preference skill
        session.activate_skill("image_preference")

        # 下载图片为 base64
        img_url = pic.url.replace("i.pximg.net", "pixiv.shewinder.win")
        base64_image = await _download_image_to_base64(img_url)

        # 构造消息
        tags_str = ", ".join(pic.tags[:10])
        text = (
            f"#图片点评\n"
            f"标题:{pic.title}\n"
            f"作者:{pic.author}\n"
            f"标签:{tags_str}\n\n"
            f"用户通过{'prr' if is_r18 else 'pr'}主动查看了这张图，"
            f"默认视为对该图的隐性喜欢并更新偏好。"
            f"但如果该图的内容与用户现有画像中的核心偏好或回避内容明显冲突，"
            f"则仅作为中性浏览记录处理，不要强化偏好。"
        )

        if base64_image and api_config.get("supports_multimodal", False):
            message_content = [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": base64_image}},
            ]
            await session.store_user_image(base64_image)
        else:
            message_content = text + f"\n图片URL: {img_url}"

        session.add_message("user", message_content)

        # 执行对话，on_content=None 确保不发送中间内容
        await session.chat(
            api_config=api_config,
            bot=bot,
            event=event,
            on_content=None,
        )

    except Exception:
        pass


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


async def send_rank(sv: Service, raw_pics: List[RankPic], gids: List[int] = None, is_r18: bool = False):
    bot: Bot = get_bot_list()[0]
    if not gids:
        gids = await get_service_groups(sv_name=sv.name)
    sv.logger.info("sending pixiv rank")

    sent_pids: List[int] = []

    for gid in gids:
        # 每个群独立筛选
        pics = await filter_rank_ai(raw_pics, group_id=gid, bot=bot)

        if not pics:
            sv.logger.warning(f"群{gid} 筛选结果为空，跳过发送")
            continue

        # 缓存该群榜单
        if is_r18:
            _group_ranks_r18[gid] = pics
        else:
            _group_ranks[gid] = pics

        try:
            preview = await generate_preview(sv, pics)
            if preview is None:
                sv.logger.warning(f"群{gid} 预览图生成失败，跳过发送")
                continue

            preview_modified = anti_harmony(preview)
            await bot.send_group_msg(group_id=gid, message=R.image_from_memory(preview_modified))
            sv.logger.info(f"群{gid} 投递成功！")
            sent_pids.extend(p.pid for p in pics)
        except Exception as e:
            sv.logger.exception(e)

        await asyncio.sleep(120)

    # 更新去重记录
    if sent_pids:
        if not is_r18:
            if len(score_data.last_three_days) == 3:
                score_data.last_three_days.pop(0)
            score_data.last_three_days.append(sent_pids)
        else:
            if len(score_data.last_three_days) == 0:
                score_data.last_three_days.append([])
            score_data.last_three_days[-1].extend(sent_pids)
        save_score_data()


detail = sv.on_command("pr", handlers=[_strip_cmd])


@detail.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    arg = str(event.get_message())
    try:
        n = int(arg)
    except:
        await bot.send(event, "not a number")
        return
    if n < 1 or n > 15:
        await bot.send(event, "数字超限")
        return
    idx = n - 1

    gid = event.group_id
    rank_list = _group_ranks.get(gid)
    if not rank_list and _raw_rank:
        rank_list = await filter_rank_ai(_raw_rank, group_id=gid, bot=bot)
        _group_ranks[gid] = rank_list

    if not rank_list:
        await bot.send(event, "日榜未更新")
        return
    if idx >= len(rank_list):
        await bot.send(event, f"索引超出范围（当前共{len(rank_list)}个作品）")
        return
    p = rank_list[idx]

    await handle_msg(bot, event, f"pid {p.pid}")
    asyncio.create_task(_implicit_preference_update(bot, event, p, is_r18=False))


detail_r18 = sv_r18.on_command("prr", handlers=[_strip_cmd])


@detail_r18.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    arg = str(event.get_message())
    try:
        n = int(arg)
    except:
        await bot.send(event, "not a number")
        return
    if n < 1 or n > 15:
        await bot.send(event, "数字超限")
        return
    idx = n - 1

    gid = event.group_id
    rank_list = _group_ranks_r18.get(gid)
    if not rank_list and _raw_rank_r18:
        rank_list = await filter_rank_ai(_raw_rank_r18, group_id=gid, bot=bot)
        _group_ranks_r18[gid] = rank_list

    if not rank_list:
        await bot.send(event, "日榜未更新")
        return
    if idx >= len(rank_list):
        await bot.send(event, f"索引超出范围（当前共{len(rank_list)}个作品）")
        return
    p = rank_list[idx]

    await handle_msg(bot, event, f"pid {p.pid}")
    asyncio.create_task(_implicit_preference_update(bot, event, p, is_r18=True))


@scheduled_job("cron", hour=conf.hour, minute=conf.minute + 1, id="pixiv日榜")
async def pixiv_rank():
    await send_rank(sv, _raw_rank, is_r18=False)


@scheduled_job("cron", hour=conf.hour, minute=conf.minute + 5, id="pixiv日榜r18")
async def pixiv_rank_r18():
    await send_rank(sv_r18, _raw_rank_r18, is_r18=True)


def _get_superuser_id() -> str:
    """获取第一个 superuser 的 ID"""
    superusers = getattr(hsn_config, 'superusers', set())
    if superusers:
        su_list = list(superusers)
        return str(su_list[0])
    return "default"


async def update_rank(bot: Bot = None, event: GroupMessageEvent = None):
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    date = f"{yesterday}"

    logger.info("正在下载日榜")
    _raw_rank.clear()
    _raw_rank.extend(await get_rank(date))
    logger.info("日榜下载完成")

    logger.info("正在下载r18日榜")
    _raw_rank_r18.clear()
    _raw_rank_r18.extend(await get_rank(date, "day_r18"))
    logger.info("r18日榜下载完成")

    # 新一天榜单，清空旧的群缓存
    _group_ranks.clear()
    _group_ranks_r18.clear()

    save_score_data()


sucmd("更新日榜").handle()(update_rank)


@sucmd("预览日榜").handle()
async def _(bot: Bot, event: GroupMessageEvent):
    await send_rank(sv, _raw_rank, gids=[event.group_id], is_r18=False)
    await send_rank(sv_r18, _raw_rank_r18, gids=[event.group_id], is_r18=True)


scheduled_job("cron", hour=conf.hour, minute=conf.minute, id="pixiv日榜数据更新")(update_rank)


async def resolve_rankpic_from_arg(arg: str, group_id: int = None) -> Tuple[Optional[RankPic], Optional[str]]:
    """
    解析参数为 RankPic 对象
    
    支持两种格式：
    1. 日榜索引: "pr1", "pr2", ... (从该群榜单获取)
    2. R18日榜索引: "prr1", "prr2", ... (从该群R18榜单获取)
    
    返回: (RankPic对象, 错误消息)
    如果成功，返回 (RankPic, None)
    如果失败，返回 (None, 错误消息)
    """
    arg = arg.strip()
    
    # 检查是否为 pr<n> 格式
    pr_match = re.match(r'^pr(\d+)$', arg, re.IGNORECASE)
    if pr_match:
        try:
            n = int(pr_match.group(1))
            if n < 1 or n > 15:
                return None, "数字超限，请输入1-15之间的数字"
            
            if group_id is not None:
                rank_list = _group_ranks.get(group_id)
            else:
                rank_list = None
            if not rank_list:
                rank_list = _raw_rank
            
            if not rank_list:
                return None, "日榜未更新"
            
            if n > len(rank_list):
                return None, f"索引超出今日日榜范围（当前共{len(rank_list)}个作品）"
            
            idx = n - 1
            logger.info(f"[resolve] pr{n} -> PID:{rank_list[idx].pid}")
            return rank_list[idx], None
        except (ValueError, IndexError):
            return None, "索引格式错误"
    
    # 检查是否为 prr<n> 格式
    prr_match = re.match(r'^prr(\d+)$', arg, re.IGNORECASE)
    if prr_match:
        try:
            n = int(prr_match.group(1))
            if n < 1 or n > 15:
                return None, "数字超限，请输入1-15之间的数字"
            
            if group_id is not None:
                rank_list = _group_ranks_r18.get(group_id)
            else:
                rank_list = None
            if not rank_list:
                rank_list = _raw_rank_r18
            
            if not rank_list:
                return None, "R18日榜未更新"
            
            if n > len(rank_list):
                return None, f"索引超出今日R18日榜范围（当前共{len(rank_list)}个作品）"
            
            idx = n - 1
            logger.info(f"[resolve] prr{n} -> PID:{rank_list[idx].pid}")
            return rank_list[idx], None
        except (ValueError, IndexError):
            return None, "索引格式错误"
    
    # 都不匹配
    logger.warning(f"[resolve] 参数不匹配: {arg}")
    return None, "参数错误：请使用 pr<n> 或 prr<n>"


fav = sucmd("favor", handlers=[_strip_cmd])


@fav.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    arg = str(event.get_message()).strip()
    sv.logger.info(f"[favor] 收到参数: {arg}, user={event.user_id}, group={event.group_id}")
    
    rank_pic, error_msg = await resolve_rankpic_from_arg(arg, event.group_id)
    
    if rank_pic is None:
        sv.logger.warning(f"[favor] 解析失败: {error_msg}")
        await bot.send(event, error_msg or "请输入 pr<n> 或 prr<n>")
        return
    
    sv.logger.info(f"[favor] 解析成功: PID={rank_pic.pid}, url={rank_pic.url}")
    
    # 通过 handle_msg 触发 aichat 的 image_preference skill 分析图片并更新画像
    img_url = rank_pic.url.replace("i.pximg.net", "pixiv.shewinder.win")
    sv.logger.info(f"[favor] 准备发送图片: {img_url}")
    
    try:
        tags_str = ", ".join(rank_pic.tags[:10])
        text = f"#图片点评\n标题:{rank_pic.title}\n作者:{rank_pic.author}\n标签:{tags_str}\n\n我喜欢这张图"
        sv.logger.info(f"[favor] 文本内容: {text[:100]}")
        
        img_seg = MessageSegment.image(img_url)
        img_seg.data['url'] = img_url  # 确保 aichat 能提取到图片 URL
        msg = Message([
            MessageSegment.text(text),
            img_seg
        ])
        sv.logger.info("[favor] 消息构造完成，调用 handle_msg")
        await handle_msg(bot, event, msg)
        sv.logger.info("[favor] handle_msg 调用完成")
    except Exception as e:
        sv.logger.exception(f"[favor] 异常: {e}")
        await bot.send(event, f"处理失败: {e}")


dis = sucmd("dislike", handlers=[_strip_cmd])


@dis.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    arg = str(event.get_message()).strip()
    sv.logger.info(f"[dislike] 收到参数: {arg}, user={event.user_id}, group={event.group_id}")
    
    rank_pic, error_msg = await resolve_rankpic_from_arg(arg, event.group_id)
    
    if rank_pic is None:
        sv.logger.warning(f"[dislike] 解析失败: {error_msg}")
        await bot.send(event, error_msg or "请输入 pr<n> 或 prr<n>")
        return
    
    sv.logger.info(f"[dislike] 解析成功: PID={rank_pic.pid}, url={rank_pic.url}")
    
    img_url = rank_pic.url.replace("i.pximg.net", "pixiv.shewinder.win")
    sv.logger.info(f"[dislike] 准备发送图片: {img_url}")
    
    try:
        tags_str = ", ".join(rank_pic.tags[:10])
        text = f"#图片点评\n标题:{rank_pic.title}\n作者:{rank_pic.author}\n标签:{tags_str}\n\n我不喜欢这张图"
        sv.logger.info(f"[dislike] 文本内容: {text[:100]}")
        
        img_seg = MessageSegment.image(img_url)
        img_seg.data['url'] = img_url  # 确保 aichat 能提取到图片 URL
        msg = Message([
            MessageSegment.text(text),
            img_seg
        ])
        sv.logger.info("[dislike] 消息构造完成，调用 handle_msg")
        await handle_msg(bot, event, msg)
        sv.logger.info("[dislike] handle_msg 调用完成")
    except Exception as e:
        sv.logger.exception(f"[dislike] 异常: {e}")
        await bot.send(event, f"处理失败: {e}")
