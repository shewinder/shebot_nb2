"""AI 聊天处理模块"""
import asyncio
import base64
import os
from typing import Any, Dict, List, Optional, Tuple, Union
from loguru import logger

import httpx

from hoshino import Bot, Event
from hoshino.util import get_event_imageurl, get_event_videourl, truncate_log
from hoshino.util.message_util import extract_images_from_reply, extract_videos_from_reply

from .api import api_manager
from .config import Config
from .persona import persona_manager
from ._send_util import send_ai_response
from .chat_executor import ChatExecutor, ChatResult
from .session import (
    PendingInput,
    Session,
    format_choices_for_display,
    parse_choices_from_response,
    session_manager,
)
from .shortcuts import shortcuts_manager

conf = Config.get_instance('aichat')

# 用户视频大小上限（100MB，QQ 视频段常见上限内）
MAX_VIDEO_SIZE = 100 * 1024 * 1024


async def download_image_to_base64(image_url: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=30.0, verify=False, follow_redirects=True) as client:
            resp = await client.get(image_url)

        if resp.status_code != 200:
            logger.error(f"下载图片失败: {resp.status_code}, URL: {image_url}")
            return None

        image_data = resp.content
        if not image_data:
            logger.error(f"图片数据为空: {image_url}")
            return None

        # 限制图片大小（10MB），与 store_images 工具保持一致
        if len(image_data) > 10 * 1024 * 1024:
            logger.warning(f"图片过大，跳过: {len(image_data)} bytes, URL: {image_url}")
            return None

        ext = "png"
        content_type = resp.headers.get("Content-Type", "")
        if content_type and content_type.startswith("image/"):
            # 从 Content-Type 提取格式，如 "image/jpeg" -> "jpeg"
            ext = content_type.split("/")[1].split(";")[0].strip()
            # 标准化格式名称
            if ext == "jpeg":
                ext = "jpg"
        else:
            if "." in image_url:
                url_ext = os.path.splitext(image_url.split("?")[0])[1].lower()
                if url_ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                    ext = url_ext.lstrip(".")

        base64_data = base64.b64encode(image_data).decode('utf-8')
        image_url_data = f"data:image/{ext};base64,{base64_data}"
        return image_url_data
    except Exception as e:
        logger.exception(f"处理图片失败: {e}, URL: {image_url}")
        return None


async def send_response(
    bot: Bot,
    event: Event,
    content: str,
    session: Session,
    enable_markdown: bool = False,
    markdown_min_length: int = 100,
) -> bool:
    """统一发送 AI 回复内容，支持 Markdown 渲染、图片提取和图片标识符"""
    return await send_ai_response(
        content, session,
        group_id=getattr(event, 'group_id', None),
        user_id=event.user_id,
        enable_markdown=enable_markdown,
        markdown_min_length=markdown_min_length,
    )


async def handle_ai_chat(bot: Bot, event: Event):
    # 获取消息内容
    msg = str(event.message).strip()

    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    # 先检查是否有活跃 session（不创建）
    session = session_manager.get_session(user_id, group_id)
    in_continuous_mode = session.continuous_mode if session else False

    if msg.startswith('#'):
        user_input = msg[1:].strip()
        # 检查快捷指令（支持参数覆盖，如 #角色扮演 model=WAI-illustrious）
        shortcut_name = user_input.split()[0] if user_input else ""
        shortcut = shortcuts_manager.get_shortcut(shortcut_name)
        if shortcut:
            overrides = {}
            positional = []
            for part in user_input.split()[1:]:
                if '=' in part:
                    k, v = part.split('=', 1)
                    overrides[k] = v
                else:
                    positional.append(part)
            rendered = shortcuts_manager.render_prompt(shortcut_name, overrides, positional)
            if rendered:
                user_input = rendered
                logger.info(f"触发快捷指令「{shortcut.name}」")
    elif in_continuous_mode:
        user_input = msg
    else:
        return

    api_config = api_manager.get_api_config()
    if not api_config or not api_config.get("api_key"):
        await bot.send(event, "AI 服务未配置或当前模型不可用，请联系超级用户配置或切换模型")
        return

    image_urls = get_event_imageurl(event)

    try:
        image_urls.extend(await extract_images_from_reply(event, bot))
    except Exception as e:
        logger.warning(f"提取引用消息图片异常: {type(e).__name__}: {e}")

    video_urls = get_event_videourl(event)
    try:
        video_urls.extend(await extract_videos_from_reply(event, bot))
    except Exception as e:
        logger.warning(f"提取引用消息视频异常: {type(e).__name__}: {e}")

    if getattr(event, "reply", None):
        # 引用消息媒体提取计数：便于诊断"转发媒体未进入对话"
        logger.info(f"引用消息媒体提取：图片 {len(image_urls)} 个，视频 {len(video_urls)} 个")
    elif image_urls or video_urls:
        logger.info(f"媒体提取：图片 {len(image_urls)} 个，视频 {len(video_urls)} 个")

    persona = persona_manager.get_persona(user_id, group_id)
    # 同步获取或创建，避免并发首消息在检查与创建之间覆盖会话。
    session = session_manager.get_or_create_session(user_id, group_id, persona)

    is_owner, sequence, turn_id, preceding = session.claim_turn_or_enqueue(
        user_input, image_urls, video_urls, bot, event, msg,
    )
    if not is_owner:
        await _ack_pending_input(session, bot, event, sequence, turn_id)
        return

    # session.lock 仍保护历史提交；后续入口只访问 pending inbox。
    async with session.lock:
        try:
            first = PendingInput(
                user_input=user_input,
                image_urls=list(image_urls),
                video_urls=list(video_urls),
                bot=bot,
                event=event,
                raw_message=msg,
            )
            await _run_turn(session, first, api_config, preceding)
        finally:
            session.end_turn(turn_id)


async def _ack_pending_input(
    session: Session,
    bot: Bot,
    event: Event,
    sequence: Optional[int],
    turn_id: Optional[str],
) -> None:
    """确认消息已进入运行中会话，不等待主会话锁。"""
    if sequence is None:
        await bot.send(event, "当前对话的待处理消息已满，请稍后再发")
        return
    logger.info(
        f"[RuntimeInsert] session={session.session_id} turn={turn_id} "
        f"sequence={sequence} queued={session.pending_input_count()}"
    )
    await bot.send(event, "消息已加入当前对话，将在下一个可用节点处理")


def _resolve_choice(
    session: Session,
    item: PendingInput,
    choices: Optional[Dict[int, str]] = None,
) -> str:
    """在消息真正执行时解析选项，避免入队期间固定过期 choices。"""
    user_input = item.user_input
    if item.raw_message not in {'1', '2', '3'}:
        return user_input
    if choices is None:
        choices = session.get_last_choices()
    choice_num = int(item.raw_message)
    if choice_num in choices:
        user_input = choices[choice_num]
        logger.info(f"用户选择选项 {choice_num}: {user_input}")
    return user_input


async def _run_turn(
    session: Session,
    first: PendingInput,
    api_config: Dict[str, Any],
    preceding: Optional[List[PendingInput]] = None,
) -> None:
    """单一执行者处理首条消息，并在安全边界按 FIFO 续接插入消息。"""
    current_batch = list(preceding or []) + [first]
    while current_batch:
        for index, item in enumerate(current_batch):
            try:
                completed = await _run_chat(
                    item.bot,
                    item.event,
                    session,
                    _resolve_choice(session, item),
                    item.image_urls,
                    item.video_urls,
                    api_config,
                )
                if completed is False:
                    remaining = current_batch[index:]
                    if item is first:
                        remaining = current_batch[index + 1:]
                    session.requeue_pending_inputs(remaining)
                    return
            except Exception:
                remaining = current_batch[index:]
                if item is first:
                    remaining = current_batch[index + 1:]
                session.requeue_pending_inputs(remaining)
                raise
        current_batch = session.finish_turn_or_drain_pending_inputs()


async def download_video(video_url: str) -> Optional[bytes]:
    """下载视频字节（上限 100MB）"""
    try:
        async with httpx.AsyncClient(timeout=60.0, verify=False, follow_redirects=True) as client:
            resp = await client.get(video_url)

        if resp.status_code != 200:
            logger.error(f"下载视频失败: {resp.status_code}, URL: {video_url}")
            return None

        data = resp.content
        if not data:
            logger.error(f"视频数据为空: {video_url}")
            return None

        if len(data) > MAX_VIDEO_SIZE:
            logger.warning(f"视频过大，跳过: {len(data)} bytes, URL: {video_url}")
            return None

        return data
    except Exception as e:
        logger.exception(f"下载视频失败: {e}, URL: {video_url}")
        return None


def _build_media_anchor_message(
    session: "Session",
    image_ids: List[str],
    video_ids: List[str],
) -> Optional[str]:
    """构建单条用户媒体锚定消息（一次发送合并为一条，与用户行为一致）

    单张/单个带元信息，多张只列标识符（避免消息过长）。
    """
    parts: List[str] = []

    if len(image_ids) == 1:
        entry = session._image_store.get(image_ids[0])
        if entry:
            dim = f"{entry.width}x{entry.height}" if entry.width and entry.height else "未知尺寸"
            parts.append(f"用户发送了图片：{image_ids[0]}（{entry.format} {dim}，已保存）")
        else:
            parts.append(f"用户发送了图片：{image_ids[0]}（已保存）")
    elif image_ids:
        parts.append(f"用户发送了 {len(image_ids)} 张图片：{'、'.join(image_ids)}（已保存）")

    if len(video_ids) == 1:
        entry = session._video_store.get(video_ids[0])
        if entry:
            size_kb = entry.size_bytes // 1024
            parts.append(f"用户发送了视频：{video_ids[0]}（{entry.format} {size_kb}KB，已保存）")
        else:
            parts.append(f"用户发送了视频：{video_ids[0]}（已保存）")
    elif video_ids:
        parts.append(f"用户发送了 {len(video_ids)} 个视频：{'、'.join(video_ids)}（已保存）")

    return "；".join(parts) if parts else None


def _insert_media_anchor(session: "Session", anchor: Optional[str]) -> None:
    """把用户媒体锚定消息插入会话历史（紧随用户消息，一次发送仅一条）"""
    if anchor:
        session.add_raw_message({"role": "user", "content": anchor})


async def _append_user_input(
    bot: Bot,
    event: Event,
    session: Session,
    user_input: str,
    image_urls: List[str],
    video_urls: List[str],
    api_config: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], bool]:
    """准备用户文本与媒体，写入历史并返回本次新增的 API 消息。"""
    history_start = len(session.messages)
    supports_multimodal = api_config.get("supports_multimodal", False)
    message_content: Union[str, List[Dict[str, Any]]]
    # 用户媒体标识符（一次用户消息合并为一条锚定消息，与用户行为一致）
    user_image_ids: List[str] = []
    user_video_ids: List[str] = []

    # 用户视频：并行下载再存储（串行下载大视频会长时间卡住对话）
    if video_urls:
        downloaded = await asyncio.gather(*[download_video(u) for u in video_urls])
        for video_url, video_bytes in zip(video_urls, downloaded):
            if video_bytes:
                identifier = await session.store_user_video(video_bytes, url=video_url)
                user_video_ids.append(identifier)
                logger.info(f"存储用户视频: {identifier}")
            else:
                logger.warning(f"视频处理失败，跳过: {video_url}")

    if image_urls and not supports_multimodal:
        # 并行下载（转发多图不再串行卡顿），按原顺序存储
        downloaded = await asyncio.gather(*[download_image_to_base64(u) for u in image_urls])
        for img_url, base64_image in zip(image_urls, downloaded):
            if base64_image:
                identifier = await session.store_user_image(base64_image, url=img_url)
                user_image_ids.append(identifier)
                logger.info(f"存储用户图片: {identifier} (模型不支持多模态，可通过工具使用)")
            else:
                logger.warning(f"图片处理失败，跳过: {img_url}")

        if user_input:
            logger.debug(f"模型 {api_config.get('model')} 不支持多模态，图片已存储，仅发送文本")
            message_content = user_input
        else:
            _insert_media_anchor(session, _build_media_anchor_message(session, user_image_ids, user_video_ids))
            await bot.send(event, f"图片已接收并保存。当前模型不支持直接识别图片，你可以通过工具（如 #编辑图片）来处理这些图片。")
            return [dict(message) for message in session.messages[history_start:]], False
    elif image_urls and supports_multimodal:
        content_parts: List[Dict[str, Any]] = []

        downloaded = await asyncio.gather(*[download_image_to_base64(u) for u in image_urls])
        for img_url, base64_image in zip(image_urls, downloaded):
            if base64_image:
                identifier = await session.store_user_image(base64_image, url=img_url)
                user_image_ids.append(identifier)
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": base64_image,
                    },
                })
                logger.info(f"存储用户图片: {identifier}, 用户: {event.user_id}, 群组: {getattr(event, 'group_id', None)}")
            else:
                logger.warning(f"图片处理失败，跳过: {img_url}")

        if not content_parts and not user_input:
            await bot.send(event, "图片处理失败，请重试或提供文本内容")
            return [], False

        if user_input:
            content_parts.append({
                "type": "text",
                "text": user_input,
            })

        if not user_input and content_parts:
            content_parts.append({
                "type": "text",
                "text": "请描述图片的内容。",
            })

        message_content = content_parts if content_parts else user_input
    else:
        if not user_input:
            if user_video_ids:
                # 仅媒体（如用户只发视频）：锚定后结束本轮，供后续轮次引用
                _insert_media_anchor(session, _build_media_anchor_message(session, user_image_ids, user_video_ids))
                await bot.send(event, "视频已接收并保存。当前无法直接分析视频内容，你可以让我基于它执行任务（如视频续写）。")
            else:
                await bot.send(event, "请输入要询问的内容（#后面）")
            return [dict(message) for message in session.messages[history_start:]], False
        message_content = user_input

    session.add_message("user", message_content)
    # 用户媒体锚定：紧随用户消息插入（一次发送合并为一条）
    _insert_media_anchor(session, _build_media_anchor_message(session, user_image_ids, user_video_ids))
    return [dict(message) for message in session.messages[history_start:]], True


async def _run_chat(
    bot: Bot,
    event: Event,
    session: Session,
    user_input: str,
    image_urls: List[str],
    video_urls: List[str],
    api_config: Dict[str, Any],
) -> bool:
    """会话锁内的实际对话编排：构建消息 → 执行 → 回写历史 → 发送。"""
    history_checkpoint = len(session.messages)
    absorbed_pending: List[PendingInput] = []
    try:
        _, should_invoke = await _append_user_input(
            bot, event, session, user_input, image_urls, video_urls, api_config,
        )
    except Exception:
        del session.messages[history_checkpoint:]
        session.save_snapshot()
        raise
    if not should_invoke:
        return True

    async def on_content(content: str):
        if content and content.strip():
            await send_response(
                bot, event, content, session,
                enable_markdown=conf.enable_markdown_render,
                markdown_min_length=conf.markdown_min_length
            )

    async def before_next_request() -> List[Dict[str, Any]]:
        """在 tool results 完整写回后吸收当前全部插入消息。"""
        pending = session.drain_pending_inputs()
        if not pending:
            return []
        inserted: List[Dict[str, Any]] = []
        pending_choices = session.get_last_choices()
        for index, item in enumerate(pending):
            try:
                messages, _ = await _append_user_input(
                    item.bot,
                    item.event,
                    session,
                    _resolve_choice(session, item, pending_choices),
                    item.image_urls,
                    item.video_urls,
                    api_config,
                )
                inserted.extend(messages)
                absorbed_pending.append(item)
            except Exception:
                session.requeue_pending_inputs(pending[index:])
                raise
        return inserted

    try:
        api_result = await ChatExecutor(session).chat(
            api_config=api_config,
            bot=bot,
            event=event,
            on_content=on_content,
            before_next_request=before_next_request,
        )
    except Exception:
        # 媒体准备或 API 编排异常时，回滚本批次并保留已吸收的插入消息。
        del session.messages[history_checkpoint:]
        session.save_snapshot()
        session.requeue_pending_inputs(absorbed_pending)
        raise

    # 工具图片输出已由 send_response 通过标识符处理，无需重复发送
    # 注意：旧版 _image_urls 机制已废弃，请使用标识符机制 <ai_image_N>

    if api_result.error and not api_result.content:
        # 仅回滚本批次；插入消息重新入队，等待下一次可用回合。
        del session.messages[history_checkpoint:]
        session.save_snapshot()
        session.requeue_pending_inputs(absorbed_pending)
        await bot.send(event, f"AI服务暂时不可用，请稍后再试\n错误: {api_result.error}")
        return False

    response = api_result.content or ""
    assistant_msg = {"role": "assistant", "content": response}
    if api_result.reasoning_content:
        assistant_msg["reasoning_content"] = api_result.reasoning_content
    session.add_raw_message(assistant_msg)

    content, choices = parse_choices_from_response(response)
    if not choices:
        choices = session.get_last_choices()

    if choices:
        display_response = content + format_choices_for_display(choices)
    else:
        display_response = content

    try:
        if not display_response:
            await bot.send(event, "抱歉，我没有生成任何内容，请重试")
            return True

        await send_response(
            bot, event, display_response, session,
            enable_markdown=conf.enable_markdown_render,
            markdown_min_length=conf.markdown_min_length
        )
    except Exception as e:
        logger.error(truncate_log(str(display_response)))
        logger.error(f"发送AI回复失败: {e}")
    return True
