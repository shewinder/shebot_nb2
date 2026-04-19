"""AI 聊天处理模块"""
import base64
import json
import os
from typing import Any, Dict, List, Optional, Union
from loguru import logger

from hoshino import Bot, Event
from hoshino.util import aiohttpx, get_event_imageurl, truncate_log, log_json
from hoshino.util.message_util import extract_images_from_reply, send_group_forward_msg
from hoshino import MessageSegment

from .api import api_manager
from .config import Config
from .md_render import strip_thinking_tags
from .persona import persona_manager
from .session import session_manager, ChatResult, Session, parse_choices_from_response, format_choices_for_display
from .shortcuts import shortcuts_manager

conf = Config.get_instance('aichat')


async def download_image_to_base64(image_url: str) -> Optional[str]:
    try:
        resp = await aiohttpx.get(image_url)
        if not resp.ok:
            logger.error(f"下载图片失败: {resp.status_code}, URL: {image_url}")
            return None
        
        image_data = resp.content
        if not image_data:
            logger.error(f"图片数据为空: {image_url}")
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
    if not content or not content.strip():
        return False
    
    # 构建消息列表（根据 Markdown 设置采用不同策略）
    messages = await session.build_message(
        content,
        enable_markdown=enable_markdown,
        markdown_min_length=markdown_min_length
    )
    
    messages = [m for m in messages if m]
    if not messages:
        return False
    
    group_id: Optional[int] = getattr(event, 'group_id', None)
    
    if group_id and len(messages) > 1:
        try:
            msg_segments: List[MessageSegment] = []
            for msg in messages:
                msg_segments.extend(msg)
            await send_group_forward_msg(bot, group_id, msg_segments)
            return True
        except Exception as e:
            logger.warning(f"转发消息发送失败，降级为逐条发送: {e}")
    
    success_count = 0
    for i, msg in enumerate(messages):
        try:
            await bot.send(event, msg)
            success_count += 1
        except Exception as e:
            logger.error(f"发送第 {i+1}/{len(messages)} 条消息失败: {e}")
    
    return success_count > 0


async def handle_ai_chat(bot: Bot, event: Event):
    # 获取消息内容
    msg = str(event.message).strip()
    
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    in_continuous_mode = session_manager.is_continuous_mode(user_id, group_id)
    last_choices = session_manager.get_last_choices(user_id, group_id)
    
    if msg.startswith('#'):
        user_input = msg[1:].strip()
        # 检查快捷指令
        shortcut = shortcuts_manager.get_shortcut(user_input)
        if shortcut:
            user_input = shortcut.prompt
            logger.info(f"触发快捷指令「{shortcut.name}」")
    elif in_continuous_mode:
        user_input = msg
    else:
        return
    
    if last_choices:
        if msg in ['1', '2', '3']:
            choice_num = int(msg)
            if choice_num in last_choices:
                # 将数字替换为选项内容
                user_input = last_choices[choice_num]
                logger.info(f"用户选择选项 {choice_num}: {user_input}")

    api_config = api_manager.get_api_config()
    if not api_config or not api_config.get("api_key"):
        await bot.send(event, "AI 服务未配置或当前模型不可用，请联系超级用户配置或切换模型")
        return

    image_urls = get_event_imageurl(event)
    
    image_urls.extend(await extract_images_from_reply(event, bot))
    logger.info(f"检测到图片URL: {image_urls}")
    
    supports_multimodal = api_config.get("supports_multimodal", False)
    message_content: Union[str, List[Dict[str, Any]]]
    
    persona = persona_manager.get_persona(user_id, group_id)
    session = session_manager.get_session(user_id, group_id, persona)
    
    if image_urls and not supports_multimodal:
        for img_url in image_urls:
            base64_image = await download_image_to_base64(img_url)
            if base64_image:
                identifier = await session.store_user_image(base64_image)
                logger.info(f"存储用户图片: {identifier} (模型不支持多模态，可通过工具使用)")
            else:
                logger.warning(f"图片处理失败，跳过: {img_url}")
        
        if user_input:
            logger.debug(f"模型 {api_config.get('model')} 不支持多模态，图片已存储，仅发送文本")
            message_content = user_input
        else:
            await bot.send(event, f"图片已接收并保存。当前模型不支持直接识别图片，你可以通过工具（如 #编辑图片）来处理这些图片。")
            return
    elif image_urls and supports_multimodal:
        content_parts: List[Dict[str, Any]] = []
        
        for img_url in image_urls:
            base64_image = await download_image_to_base64(img_url)
            if base64_image:
                identifier = await session.store_user_image(base64_image)
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": base64_image,
                    },
                })
                logger.info(f"存储用户图片: {identifier}, 用户: {user_id}, 群组: {group_id}")
            else:
                logger.warning(f"图片处理失败，跳过: {img_url}")
        
        if not content_parts and not user_input:
            await bot.send(event, "图片处理失败，请重试或提供文本内容")
            return
        
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
            await bot.send(event, "请输入要询问的内容（#后面）")
            return
        message_content = user_input

    session.add_message("user", message_content)
    pre_chat_length = len(session.messages)
    
    async def on_content(content: str):
        if content and content.strip():
            await send_response(
                bot, event, content, session,
                enable_markdown=conf.enable_markdown_render,
                markdown_min_length=conf.markdown_min_length
            )
    
    # 使用 Session 内聚的 chat 方法（自动处理消息构建和工具获取）
    api_result = await session.chat(
        api_config=api_config,
        bot=bot,
        event=event,
        on_content=on_content,
    )
    
    # 工具图片输出已由 send_response 通过标识符处理，无需重复发送
    # 注意：旧版 _image_urls 机制已废弃，请使用标识符机制 <ai_image_N>
    
    if api_result.error and not api_result.content:
        await bot.send(event, f"AI服务暂时不可用，请稍后再试\n错误: {api_result.error}")
        # 回滚到本轮 chat 之前的状态
        session.messages = session.messages[:pre_chat_length - 1]
        return
    
    response = api_result.content or ""
    
    display_response = response
    
    content, choices = parse_choices_from_response(response)
    if choices:
        display_response = content + format_choices_for_display(choices)
    else:
        display_response = response
    session.add_message("assistant", response)
    
    try:
        if not display_response:
            await bot.send(event, "抱歉，我没有生成任何内容，请重试")
            return
        
        await send_response(
            bot, event, display_response, session,
            enable_markdown=conf.enable_markdown_render,
            markdown_min_length=conf.markdown_min_length
        )
    except Exception as e:
        logger.error(truncate_log(str(display_response)))
        logger.error(f"发送AI回复失败: {e}")
