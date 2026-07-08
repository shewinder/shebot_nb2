import asyncio
import base64
import datetime
import json
import os
from pathlib import Path
import re
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from hoshino import (
    Bot,
    Message,
    MessageSegment,
    Service,
    font_dir,
    get_bot_list,
    scheduled_job,
    sucmd,
    userdata_dir,
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
from hoshino.modules.aichat.aichat.chat_executor import ChatExecutor

from .config import Config
from .data_source import RankPic, filter_rank, filter_rank_ai, get_rank, get_rankpic, read_group_preferences, not_sent_in_3_days
from .vision_filter import is_vision_filter_available, vision_filter_multi_group
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


def _rank_data_dir():
    d = userdata_dir.joinpath('pixiv')
    if not d.exists():
        d.mkdir(parents=True)
    return d


def _rank_log_dir(date_str: str = None) -> Path:
    if date_str is None:
        date_str = str(datetime.date.today())
    d = _rank_data_dir().joinpath('rank_logs', date_str)
    if not d.exists():
        d.mkdir(parents=True)
    return d


def _save_rank_log(group_id: int, log: dict, suffix: str = ""):
    """保存群日榜筛选日志"""
    date_str = str(datetime.date.today())
    log["timestamp"] = datetime.datetime.now().isoformat()
    log["group_id"] = group_id
    name = f"{group_id}{suffix}.json"
    p = _rank_log_dir(date_str).joinpath(name)
    p.write_text(json.dumps(log, ensure_ascii=False, indent=2))
    logger.info(f"群 {group_id}{suffix} 筛选日志已保存: {p}")


def _read_rank_log(group_id: int, date_str: str, suffix: str = "") -> Optional[dict]:
    """读取指定日期的群筛选日志"""
    name = f"{group_id}{suffix}.json"
    p = _rank_log_dir(date_str).joinpath(name)
    if p.exists():
        return json.loads(p.read_text())
    return None


def _pic_to_dict(p: RankPic) -> dict:
    return {
        "pid": p.pid,
        "url": p.url,
        "tags": p.tags,
        "score": p.score,
        "page_count": p.page_count,
        "author": p.author,
        "author_id": p.author_id,
        "urls": p.urls,
        "title": p.title,
    }


def _dict_to_pic(d: dict) -> RankPic:
    return RankPic(
        pid=d["pid"],
        url=d["url"],
        tags=d["tags"],
        score=d.get("score", 0),
        page_count=d.get("page_count", 1),
        author=d["author"],
        author_id=d["author_id"],
        urls=d.get("urls", [d["url"]]),
        title=d.get("title", ""),
    )


def _save_rank_data():
    yesterday = str(datetime.date.today() - datetime.timedelta(days=1))
    for key, raw_pics, group_ranks, label in [
        ("pixiv_rank.json", _raw_rank, _group_ranks, "日榜"),
        ("pixiv_rank_r18.json", _raw_rank_r18, _group_ranks_r18, "R18日榜"),
    ]:
        p = _rank_data_dir().joinpath(key)
        data = {
            "date": yesterday,
            "raw": [_pic_to_dict(x) for x in raw_pics],
            "groups": {
                str(gid): [_pic_to_dict(x) for x in pics]
                for gid, pics in group_ranks.items()
            },
        }
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        logger.info(f"{label}数据已持久化: raw={len(raw_pics)}, groups={len(group_ranks)}")


def _load_rank_data():
    for key, raw_target, group_target, label in [
        ("pixiv_rank.json", _raw_rank, _group_ranks, "日榜"),
        ("pixiv_rank_r18.json", _raw_rank_r18, _group_ranks_r18, "R18日榜"),
    ]:
        p = _rank_data_dir().joinpath(key)
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
            for pic_data in data.get("raw", []):
                raw_target.append(_dict_to_pic(pic_data))
            for gid_str, pic_list in data.get("groups", {}).items():
                group_target[int(gid_str)] = [_dict_to_pic(x) for x in pic_list]
            logger.info(f"从磁盘加载{label}数据: raw={len(raw_target)}, groups={len(group_target)}")
        except Exception as e:
            logger.warning(f"加载{label}数据失败: {e}")


_load_rank_data()


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
    """后台任务：静默调用 aichat 更新用户画像，不向用户发送任何消息"""
    user_id = event.user_id
    group_id = event.group_id
    label = f"[preference] user={user_id} pid={pic.pid}"

    try:
        api_config = api_manager.get_api_config()
        if not api_config or not api_config.get("api_key"):
            logger.info(f"{label} 跳过: 无可用 API 配置")
            return

        logger.info(f"{label} 开始隐式偏好更新")

        session_id = f"private_{user_id}_pixivrank"
        persona = persona_manager.get_persona(user_id, group_id)
        session = Session(session_id, user_id, persona=persona, group_id=group_id, register=True)
        logger.info(f"{label} Session 已创建 (persona_len={len(persona or '')})")

        ok, msg, _ = session.activate_skill("image_preference")
        logger.info(f"{label} 激活 image_preference: {msg}")

        img_url = pic.url.replace("i.pximg.net", "pixiv.shewinder.win")
        base64_image = await _download_image_to_base64(img_url)
        if base64_image:
            logger.info(f"{label} 图片下载成功 ({len(base64_image)} chars)")
        else:
            logger.warning(f"{label} 图片下载失败，降级为纯文本")

        tags_str = ", ".join(pic.tags[:10])
        supports_multimodal = api_config.get("supports_multimodal", False) and base64_image
        text = (
            f"#图片点评\n"
            f"标题:{pic.title}\n"
            f"作者:{pic.author}\n"
            f"标签:{tags_str}\n\n"
            f"用户通过{'prr' if is_r18 else 'pr'}查看了这张图（来源: pr查看）。"
            f"pr查看属于低权重信号——用户可能感兴趣，也可能是好奇浏览。"
            f"不要以此单独支撑高评级偏好。"
            f"若内容与现有画像核心偏好一致，可作为轻微正反馈记录；"
            f"若与现有回避内容冲突，标记为中性浏览。"
            f"如果你不具备图像能力，必要时你可以调用delegate_task工具委托任务"
        )

        if supports_multimodal:
            message_content = [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": base64_image}},
            ]
            await session.store_user_image(base64_image)
        else:
            message_content = text
            await session.store_user_image(base64_image)

        session.add_message("user", message_content)
        logger.info(f"{label} 消息已加入 Session (multimodal={supports_multimodal})")

        # on_content=None: 不向用户流式输出任何内容
        # 返回值忽略: 仅用于更新偏好文件，不回复消息
        result = await ChatExecutor(session).chat(
            api_config=api_config,
            bot=bot,
            event=event,
            on_content=None,
        )
        logger.info(f"{label} 对话完成 (content_len={len(result.content or '')}, "
                    f"error={result.error}, usage={result.usage})")

    except Exception as e:
        logger.warning(f"{label} 异常: {e}")


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

    # 跨群合并：提前汇总所有群的用户画像，一次 vision 调用
    group_pids: Dict[int, List[int]] = {}
    group_vision_logs: Dict[int, Dict] = {}
    if conf.vision_filter_enabled and is_vision_filter_available() and conf.ai_filter_enabled:
        group_prefs: Dict[int, List] = {}
        for gid in gids:
            prefs = await read_group_preferences(gid, bot)
            if prefs:
                group_prefs[gid] = prefs

        if group_prefs:
            deduped = list(filter(not_sent_in_3_days, raw_pics))
            sv.logger.info(f"跨群 Vision 去重: {len(raw_pics)} → {len(deduped)} 张")
            images = [
                {"pid": p.pid, "title": p.title, "author": p.author, "tags": p.tags, "url": p.url}
                for p in deduped
            ]
            try:
                group_pids, group_vision_logs = await vision_filter_multi_group(images, group_prefs)
                sv.logger.info(
                    f"跨群 Vision 合并完成: {len(group_pids)}/{len(gids)} 个群有结果, "
                    f"覆盖 {sum(len(v) for v in group_pids.values())} 个作品"
                )
            except Exception as e:
                sv.logger.warning(f"跨群 Vision 合并失败: {e}，退回独立筛选")

    for gid in gids:
        # 每个群筛选（跨群合并时传入预选 PID）
        pre_selected = group_pids.get(gid)
        pics, filter_log = await filter_rank_ai(raw_pics, group_id=gid, bot=bot, pre_selected_pids=pre_selected)

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
            if filter_log:
                filter_log["is_r18"] = is_r18
                if gid in group_vision_logs:
                    filter_log["vision"] = group_vision_logs[gid]
                _save_rank_log(gid, filter_log, suffix="_r18" if is_r18 else "")
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
        rank_list, _ = await filter_rank_ai(_raw_rank, group_id=gid, bot=bot)
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
        rank_list, _ = await filter_rank_ai(_raw_rank_r18, group_id=gid, bot=bot)
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
    _save_rank_data()


@scheduled_job("cron", hour=conf.hour, minute=conf.minute + 5, id="pixiv日榜r18")
async def pixiv_rank_r18():
    await send_rank(sv_r18, _raw_rank_r18, is_r18=True)
    _save_rank_data()


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
    _save_rank_data()


sucmd("更新日榜").handle()(update_rank)


@sucmd("预览日榜").handle()
async def _(bot: Bot, event: GroupMessageEvent):
    await send_rank(sv, _raw_rank, gids=[event.group_id], is_r18=False)
    await send_rank(sv_r18, _raw_rank_r18, gids=[event.group_id], is_r18=True)
    _save_rank_data()


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


_filter_log = sv.on_command("筛选日志", handlers=[_strip_cmd])


@_filter_log.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    arg = str(event.get_message()).strip()
    gid = event.group_id

    date_str = arg if arg else str(datetime.date.today())
    # 验证日期格式
    try:
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await bot.send(event, "日期格式错误，请使用 YYYY-MM-DD")
        return

    lines = []
    for suffix, label in [("", "日榜"), ("_r18", "R18日榜")]:
        log = _read_rank_log(gid, date_str, suffix)
        if not log:
            continue
        vision = log.get("vision") or {}
        users = log.get("users", []) or vision.get("users", [])
        model_count = log.get("model_selected_count", log.get("ai_selected_count", 0))
        source = log.get("selection_source", "")
        model_label = "Vision 选中" if source == "vision" or vision.get("mode") == "score_matrix" else "AI 选中"
        random_count = log.get("random_count", 0)
        fallback_count = log.get("fallback_count", 0)
        final_pids = log.get("final_pids", [])

        lines.append(f"📊 {label} | {date_str}")
        lines.append(f"👥 参与画像 ({len(users)}人):")
        for u in users:
            su_tag = "[SU] " if u.get("is_superuser") else ""
            uid = u.get("user_id", "?")
            summary = " ".join(str(u.get("summary") or u.get("profile") or "").split())[:80]
            selected = u.get("selected_pids", [])
            lines.append(f"  - {su_tag}{uid}: {summary}")
            if selected:
                lines.append(f"    选中: {', '.join(str(p) for p in selected)}")

        lines.append(f"🤖 {model_label}: {model_count} 张")
        if log.get("vote_details"):
            lines.append("  投票明细:")
            for pid, voters in log["vote_details"].items():
                voter_ids = [users[v["user_idx"]]["user_id"] if v["user_idx"] < len(users) else "?"
                           for v in voters]
                lines.append(f"    PID:{pid} ← {', '.join(voter_ids)}")

        vision_scores: Dict[str, Any] = vision.get("scores", {})
        if vision_scores:
            ranked_pids = vision.get("group_sorted_pids") or vision.get("sorted_pids") or final_pids
            lines.append("🎯 Vision评分Top:")
            shown = 0
            for pid in ranked_pids:
                info = vision_scores.get(str(pid))
                if not info:
                    continue
                lines.append(
                    f"    PID:{pid} final={info.get('final_score')} avg={info.get('avg_score')} "
                    f"高={info.get('high_count')} 低={info.get('low_count')} 风险={info.get('risk_count')}"
                )
                per_user = info.get("per_user", [])
                reason = next((str(item.get("reason", "")) for item in per_user if item.get("reason")), "")
                if reason:
                    lines.append(f"      {reason[:80]}")
                shown += 1
                if shown >= 5:
                    break

        if random_count:
            random_pids = log.get("random_filled", [])
            lines.append(f"🎲 随机补齐: {random_count} 张 ({', '.join(str(p) for p in random_pids)})")
        if fallback_count:
            fallback_pids = log.get("fallback_filled", [])
            lines.append(f"📌 顺序补齐: {fallback_count} 张 ({', '.join(str(p) for p in fallback_pids)})")

        lines.append(f"📋 最终输出 ({len(final_pids)}张): {', '.join(str(p) for p in final_pids)}")
        lines.append("")

    if not lines:
        await bot.send(event, f"未找到 {date_str} 的筛选日志\n（只有启用了AI筛选的群才会生成日志）")
        return

    await bot.send(event, "\n".join(lines))
