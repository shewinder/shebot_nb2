"""AI 聊天处理模块"""
import base64
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from loguru import logger

from io import BytesIO

from hoshino import Bot, Event, MessageSegment
from hoshino.util import aiohttpx, get_event_imageurl, truncate_log, log_json
from hoshino.util.message_util import extract_images_from_reply

from .api import api_manager
from .config import Config
from .md_render import render_text_if_markdown, strip_thinking_tags, MD_IMAGE_PATTERN
from .persona import persona_manager
from .session import session_manager, ChatResult, Session

conf = Config.get_instance('aichat')


# 选项标记的正则表达式
CHOICES_PATTERN = re.compile(r'\[CHOICES\](.*?)\[/CHOICES\]', re.DOTALL)
CHOICE_ITEM_PATTERN = re.compile(r'^(\d+)\.\s*(.+)$', re.MULTILINE)

# 图片标识符正则表达式
IMAGE_IDENTIFIER_PATTERN = re.compile(r'<(user_image_\d+|ai_image_\d+)>')


def parse_choices_from_response(response: str) -> Tuple[str, Dict[int, str]]:
    choices_dict = {}
    
    match = CHOICES_PATTERN.search(response)
    if not match:
        return response.strip(), choices_dict
    
    choices_text = match.group(1).strip()
    
    for line in choices_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        choice_match = CHOICE_ITEM_PATTERN.match(line)
        if choice_match:
            num = int(choice_match.group(1))
            content = choice_match.group(2).strip()
            if num in [1, 2, 3]:
                choices_dict[num] = content
    
    content = CHOICES_PATTERN.sub('', response).strip()
    
    return content, choices_dict


def format_choices_for_display(choices: Dict[int, str]) -> str:
    if not choices:
        return ""
    
    emoji_map = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣"}
    
    lines = [
        "\n",
        "📝 请选择接下来的行动：",
    ]
    
    for num in [1, 2, 3]:
        if num in choices:
            lines.append(f"{emoji_map[num]} {choices[num]}")
    
    return "\n".join(lines)


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


async def send_image_by_identifier(
    bot: Bot,
    event: Event,
    identifier: str,
    session: Session,
) -> bool:
    """通过标识符发送图片
    
    支持格式：<user_image_N>, <ai_image_N>（带或不带尖括号）
    """
    # 标准化标识符（确保有尖括号）
    if not identifier.startswith('<'):
        identifier = f"<{identifier}>"
    
    # 解析标识符获取数据
    image_data = session.resolve_image_identifier(identifier)
    if not image_data:
        logger.warning(f"图片标识符未找到: {identifier}")
        return False
    
    try:
        if image_data.startswith("data:image"):
            # Base64 图片
            base64_data = image_data.split(",", 1)[1]
            img_bytes = base64.b64decode(base64_data)
            await bot.send(event, MessageSegment.image(file=img_bytes))
            logger.info(f"已发送标识符图片 [{identifier}], 大小: {len(img_bytes)} bytes")
        elif image_data.startswith(("http://", "https://")):
            # URL 图片
            from hoshino.sres import Res
            img_seg = await Res.image_from_url(image_data)
            await bot.send(event, img_seg)
            logger.info(f"已发送标识符图片 [{identifier}], URL: {image_data[:50]}...")
        else:
            logger.warning(f"未知的图片数据格式: {identifier}")
            return False
        return True
    except Exception as e:
        logger.exception(f"发送标识符图片失败 [{identifier}]: {e}")
        return False


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
    
    text = content.strip()
    
    # 第一步：处理图片标识符（如 <user_image_1>, <ai_image_1>）
    image_identifiers = IMAGE_IDENTIFIER_PATTERN.findall(text)
    if image_identifiers:
        for identifier in image_identifiers:
            await send_image_by_identifier(bot, event, identifier, session)
        # 从文本中移除标识符
        text = IMAGE_IDENTIFIER_PATTERN.sub('', text).strip()
    
    # 第二步：尝试 Markdown 渲染（如果文本足够长）
    if enable_markdown and len(text) >= markdown_min_length:
        try:
            img_bytes = await render_text_if_markdown(text, min_length=markdown_min_length)
            if img_bytes:
                await bot.send(event, MessageSegment.image(BytesIO(img_bytes)))
                logger.info("Markdown 渲染成功，发送渲染后的图片")
                return True
        except Exception as render_err:
            logger.warning(f"Markdown 渲染失败: {render_err}")
    
    # 第三步：提取并发送 Markdown 图片 URL
    from .md_render import extract_image_urls
    image_urls = extract_image_urls(text)
    
    if image_urls:
        for url in image_urls:
            try:
                await bot.send(event, MessageSegment.image(url))
            except Exception as img_err:
                logger.error(f"发送图片失败: {url}, 错误: {img_err}")
        
        text_content = MD_IMAGE_PATTERN.sub('', text).strip()
        if text_content:
            await bot.send(event, text_content)
        return True
    
    # 第四步：发送纯文本（如果有内容）
    if text:
        await bot.send(event, text)
    return True


async def handle_ai_chat(bot: Bot, event: Event):
    # 获取消息内容
    msg = str(event.message).strip()
    
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    in_continuous_mode = session_manager.is_continuous_mode(user_id, group_id)
    choice_mode_enabled, choice_guideline = session_manager.get_choice_mode(user_id, group_id)
    last_choices = session_manager.get_last_choices(user_id, group_id)
    
    if msg.startswith('#'):
        user_input = msg[1:].strip()
    elif in_continuous_mode:
        user_input = msg
    else:
        return
    
    if choice_mode_enabled and last_choices:
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
                identifier = session.store_user_image(base64_image)
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
                identifier = session.store_user_image(base64_image)
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
        # 回滚到用户消息之前的状态（移除用户消息及工具调用过程中添加的消息）
        while session.messages and session.messages[-1].get("role") in ("user", "assistant", "tool"):
            session.messages.pop()
        return
    
    response = api_result.content or ""
    
    display_response = response
    
    if choice_mode_enabled and in_continuous_mode:
        content, choices = parse_choices_from_response(response)
        if choices:
            session_manager.set_last_choices(user_id, group_id, choices)
            display_response = content + format_choices_for_display(choices)
            session.add_message("assistant", content)
        else:
            session_manager.set_last_choices(user_id, group_id, {})
            session.add_message("assistant", response)
    else:
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
