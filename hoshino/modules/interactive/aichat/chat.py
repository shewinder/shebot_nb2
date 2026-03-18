"""
AI 聊天处理模块
处理 AI 对话逻辑，包括图片处理和 API 调用
"""
import base64
import os
from typing import Any, Dict, List, Optional, Union
from loguru import logger

from hoshino import Bot, Event
from hoshino.util import aiohttpx, get_event_imageurl
from hoshino.util.message_util import extract_images_from_reply

from .api import api_manager
from .persona import persona_manager
from .session import session_manager


async def download_image_to_base64(image_url: str) -> Optional[str]:
    """下载图片并转换为 base64 格式的 data URL"""
    try:
        resp = await aiohttpx.get(image_url)
        if not resp.ok:
            logger.error(f"下载图片失败: {resp.status_code}, URL: {image_url}")
            return None
        
        image_data = resp.content
        if not image_data:
            logger.error(f"图片数据为空: {image_url}")
            return None
        
        # 尝试从 Content-Type 响应头获取图片格式
        ext = "png"  # 默认格式
        content_type = resp.headers.get("Content-Type", "")
        if content_type and content_type.startswith("image/"):
            # 从 Content-Type 提取格式，如 "image/jpeg" -> "jpeg"
            ext = content_type.split("/")[1].split(";")[0].strip()
            # 标准化格式名称
            if ext == "jpeg":
                ext = "jpg"
        else:
            # 如果响应头没有，尝试从 URL 推断
            if "." in image_url:
                url_ext = os.path.splitext(image_url.split("?")[0])[1].lower()
                if url_ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                    ext = url_ext.lstrip(".")
        
        # 编码为 base64
        base64_data = base64.b64encode(image_data).decode('utf-8')
        image_url_data = f"data:image/{ext};base64,{base64_data}"
        return image_url_data
    except Exception as e:
        logger.exception(f"处理图片失败: {e}, URL: {image_url}")
        return None


async def call_ai_api(messages: List[Dict[str, Any]], api_config: Dict[str, Any]) -> Optional[str]:
    """调用 AI API，使用指定的 api_config（支持文本和多模态消息）"""
    if not api_config or not api_config.get("api_key"):
        logger.warning("AI API 未配置或密钥为空")
        return None

    if not messages:
        logger.error("消息列表为空")
        return None

    url = f"{api_config['api_base'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_config['api_key']}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": api_config["model"],
        "messages": messages,
    }
    # 只在配置了参数时才添加到 payload（避免某些模型不支持这些参数）
    if "max_tokens" in api_config:
        payload["max_tokens"] = api_config["max_tokens"]
    if "temperature" in api_config:
        payload["temperature"] = api_config["temperature"]

    try:
        resp = await aiohttpx.post(url, headers=headers, json=payload)
        if not resp.ok:
            logger.error(f"AI API 调用失败: {resp.status_code}, 响应: {resp.text}")
            return None

        result = resp.json
        if not result:
            logger.error("AI API 返回空结果")
            return None

        logger.info(str(result))

        if "choices" in result and len(result["choices"]) > 0:
            message = result["choices"][0].get("message", {})
            if "content" in message:
                return message["content"]
            logger.error(f"AI API 返回格式错误，缺少 content 字段: {result}")
            return None
        error_info = result.get("error", {})
        error_msg = error_info.get("message", "未知错误") if error_info else "返回格式错误"
        logger.error(f"AI API 返回错误: {error_msg}, 完整响应: {result}")
        return None
    except Exception as e:
        logger.exception(f"调用 AI API 异常: {e}")
        return None


async def handle_ai_chat(bot: Bot, event: Event):
    """处理AI聊天消息（支持图片多模态）"""
    # 获取消息内容
    msg = str(event.message).strip()
    
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    # 检查是否以#开头，或者处于连续对话模式
    in_continuous_mode = session_manager.is_continuous_mode(user_id, group_id)
    
    if msg.startswith('#'):
        # 移除#前缀
        user_input = msg[1:].strip()
    elif in_continuous_mode:
        # 连续对话模式，无需#前缀
        user_input = msg
    else:
        # 非连续对话模式且不以#开头，忽略
        return

    api_config = api_manager.get_api_config()
    if not api_config or not api_config.get("api_key"):
        await bot.send(event, "AI 服务未配置或当前模型不可用，请联系超级用户配置或切换模型")
        return

    # 检测消息中的图片
    image_urls = get_event_imageurl(event)
    
    # 引用消息里的图片（支持转发消息中的图片）
    image_urls.extend(await extract_images_from_reply(event, bot))
    logger.info(f"检测到图片URL: {image_urls}")
    
    # 检查模型是否支持多模态
    supports_multimodal = api_config.get("supports_multimodal", False)
    
    # 构建消息内容（支持多模态）
    message_content: Union[str, List[Dict[str, Any]]]
    
    # 如果模型不支持多模态，但有图片，则只发送文本并提示
    if image_urls and not supports_multimodal:
        if user_input:
            # 有文本内容，只发送文本，忽略图片
            logger.info(f"模型 {api_config.get('model')} 不支持多模态，忽略图片，只发送文本")
            message_content = user_input
        else:
            # 只有图片没有文本，提示用户
            await bot.send(event, f"当前模型 {api_config.get('model')} 不支持图片识别，请发送文本内容")
            return
    elif image_urls and supports_multimodal:
        # 有多模态内容：图片 + 文本
        content_parts: List[Dict[str, Any]] = []
        
        # 处理所有图片
        for img_url in image_urls:
            base64_image = await download_image_to_base64(img_url)
            if base64_image:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": base64_image,
                    },
                })
            else:
                logger.warning(f"图片处理失败，跳过: {img_url}")
        
        # 如果所有图片都处理失败，且没有文本，则返回错误
        if not content_parts and not user_input:
            await bot.send(event, "图片处理失败，请重试或提供文本内容")
            return
        
        # 如果有文本内容，添加文本部分
        if user_input:
            content_parts.append({
                "type": "text",
                "text": user_input,
            })
        
        # 如果只有图片没有文本，添加一个默认提示
        if not user_input and content_parts:
            content_parts.append({
                "type": "text",
                "text": "请描述图片的内容。",
            })
        
        message_content = content_parts if content_parts else user_input
    else:
        # 纯文本消息，检查是否有内容
        if not user_input:
            await bot.send(event, "请输入要询问的内容（#后面）")
            return
        message_content = user_input

    persona = persona_manager.get_persona(user_id, group_id)
    session = session_manager.get_session(user_id, group_id, persona)
    session.add_message("user", message_content)

    response = await call_ai_api(session.messages, api_config)
    
    if response is None:
        await bot.send(event, "AI服务暂时不可用，请稍后再试")
        # 移除刚才添加的用户消息
        if session.messages and session.messages[-1].get("role") == "user":
            session.messages.pop()
        return
    
    # 添加AI回复
    session.add_message("assistant", response)
    
    # 发送回复
    try:
        await bot.send(event, response)
    except Exception as e:
        logger.error(str(response))
        logger.error(f"发送AI回复失败: {e}")
