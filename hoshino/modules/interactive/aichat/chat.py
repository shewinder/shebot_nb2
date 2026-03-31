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
from .session import session_manager, ChatResult
from .skills import skill_manager
from .tools import get_available_tools, get_tool_function
from .tools.registry import get_injectable_params

conf = Config.get_instance('aichat')


# 选项标记的正则表达式
CHOICES_PATTERN = re.compile(r'\[CHOICES\](.*?)\[/CHOICES\]', re.DOTALL)
CHOICE_ITEM_PATTERN = re.compile(r'^(\d+)\.\s*(.+)$', re.MULTILINE)

# 选项生成提示词模板
CHOICE_MODE_PROMPT_TEMPLATE = """[选项生成模式]
请在你的回复末尾，使用以下格式为用户提供3个接下来的行动选项，格外注意[CHOICES]标签是成对出现的：
[CHOICES]
1. 选项1内容
2. 选项2内容
3. 选项3内容
[/CHOICES]
{guideline_section}
[/选项生成模式]"""


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


def build_messages_with_choice_mode(
    session_messages: List[Dict[str, Any]], 
    original_persona: Optional[str],
    guideline: Optional[str]
) -> List[Dict[str, Any]]:
    messages = []
    
    system_content = ""
    if original_persona:
        system_content = original_persona
    
    guideline_section = f"\n选项生成指导标准：{guideline}\n请根据以上指导标准生成合适的选项。" if guideline else ""
    choice_prompt = CHOICE_MODE_PROMPT_TEMPLATE.format(guideline_section=guideline_section)
    
    if system_content:
        system_content += "\n\n" + choice_prompt
    else:
        system_content = choice_prompt
    
    messages.append({"role": "system", "content": system_content})
    
    for msg in session_messages:
        if msg.get("role") != "system":
            messages.append(msg)
    
    return messages


# 可扩展的环境信息字段配置
# key: (获取函数, XML属性名, 是否仅在群聊有效)
ENV_CONTEXT_PROVIDERS: Dict[str, tuple] = {
    "user_id": (lambda e: e.user_id, "user_id", False),
    "group_id": (lambda e: getattr(e, 'group_id', None), "group_id", True),
    # 扩展示例：
    # "user_role": (lambda e: get_user_role(e), "role", False),
    # "group_name": (lambda e: get_group_name(e), "group_name", True),
}


def build_static_env_info(event: Event, fields: Optional[List[str]] = None) -> str:
    """构建静态环境信息（XML格式）
    
    Args:
        event: 消息事件
        fields: 要包含的字段列表，None 则使用默认（user_id, group_id）
    
    返回 XML 格式字符串，便于模型理解结构化数据。
    扩展方式：向 ENV_CONTEXT_PROVIDERS 添加字段配置
    """
    if fields is None:
        fields = ["user_id", "group_id"]
    
    attrs = []
    for field in fields:
        if field not in ENV_CONTEXT_PROVIDERS:
            continue
        
        getter, attr_name, group_only = ENV_CONTEXT_PROVIDERS[field]
        try:
            value = getter(event)
        except Exception:
            continue
        
        if value is None:
            continue
        
        # 群聊特有字段，在私聊中跳过
        if group_only and not getattr(event, 'group_id', None):
            continue
        
        # 注意：XML 属性值如果包含特殊字符需要转义
        # 但 user_id/group_id 通常是数字，不需要转义
        # 如果后续添加字符串字段，需要在这里处理转义
        attrs.append(f'{attr_name}="{value}"')
    
    if not attrs:
        return ""
    
    return f'<context type="environment" {" ".join(attrs)} />'


def build_messages_for_api(
    session: Any,
    persona: Optional[str],
    choice_mode: bool,
    guideline: Optional[str],
    event: Optional[Event] = None
) -> List[Dict[str, Any]]:
    from .session import Session
    
    messages: List[Dict[str, Any]] = []
    
    image_list_prompt = session.build_image_list_prompt()
    system_content = ""
    if persona:
        system_content = persona
    
    if choice_mode:
        guideline_section = f"\n选项生成指导标准：{guideline}\n请根据以上指导标准生成合适的选项。" if guideline else ""
        choice_prompt = CHOICE_MODE_PROMPT_TEMPLATE.format(guideline_section=guideline_section)
        if system_content:
            system_content += "\n\n" + choice_prompt
        else:
            system_content = choice_prompt
    
    # 注入静态环境信息（XML格式）
    if event:
        env_info = build_static_env_info(event)
        if env_info:
            if system_content:
                system_content += "\n\n" + env_info
            else:
                system_content = env_info
    
    # 添加工具提示（告知AI可调用get_current_time）
    tool_hint = "<instructions>\n你可以调用 get_current_time 工具获取当前准确时间。\n</instructions>"
    if system_content:
        system_content += "\n\n" + tool_hint
    else:
        system_content = tool_hint
    
    # 注入 SKILL 元数据和已激活 SKILL 内容
    if conf.enable_skills and hasattr(session, 'session_id'):
        # 始终注入可用 SKILL 列表（帮助 AI 自动选择）
        skill_summary = skill_manager.get_metadata_summary()
        if skill_summary:
            if system_content:
                system_content += "\n\n" + skill_summary
            else:
                system_content = skill_summary
        
        # 注入已激活 SKILL 的详细内容
        skill_content = skill_manager.get_injected_content(session.session_id)
        if skill_content:
            if system_content:
                system_content += "\n\n" + skill_content
            else:
                system_content = skill_content
    
    if system_content:
        messages.append({"role": "system", "content": system_content})
    
    # 保持 session.messages 与 API 调用一致（包含完整的 system 消息）
    # 这样 web 端调试时能看到实际发送给 AI 的完整内容
    non_system_msgs = [msg for msg in session.messages if msg.get("role") != "system"]
    if system_content:
        session.messages = [{"role": "system", "content": system_content}] + non_system_msgs
    
    messages.extend(non_system_msgs)
    
    if image_list_prompt:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content")
                if isinstance(content, list):
                    # 多模态消息：添加文本部分
                    content.append({"type": "text", "text": image_list_prompt})
                elif isinstance(content, str):
                    # 纯文本消息：拼接
                    msg["content"] = content + image_list_prompt
                break
    
    return messages


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
    enable_markdown: bool = False,
    markdown_min_length: int = 100,
) -> bool:
    """统一发送 AI 回复内容，支持 Markdown 渲染和图片提取"""
    if not content or not content.strip():
        return False
    
    text = content.strip()
    
    # 尝试 Markdown 渲染
    if enable_markdown and len(text) >= markdown_min_length:
        try:
            img_bytes = await render_text_if_markdown(text, min_length=markdown_min_length)
            if img_bytes:
                await bot.send(event, MessageSegment.image(BytesIO(img_bytes)))
                logger.info("Markdown 渲染成功，发送渲染后的图片")
                return True
        except Exception as render_err:
            logger.warning(f"Markdown 渲染失败: {render_err}")
    
    # 提取并发送图片 URL
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
    
    # 纯文本发送
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
    messages_for_api = build_messages_for_api(
        session, persona, choice_mode_enabled and in_continuous_mode, choice_guideline, event
    )

    tool_context = {
        "bot": bot,
        "event": event,
    }
    
    async def on_content(content: str):
        if content and content.strip():
            await send_response(
                bot, event, content,
                enable_markdown=conf.enable_markdown_render,
                markdown_min_length=conf.markdown_min_length
            )
    
    # 使用 Session 内聚的 chat 方法
    api_result = await session.chat(
        api_config=api_config,
        tools=get_available_tools() if api_config.get("supports_tools", False) else None,
        on_content=on_content,
        context=tool_context,
    )
    
    # 处理工具图片输出
    for tool_result in api_result.tool_results:
        image_urls = tool_result["result"].get("_image_urls", [])
        try:
            for i, url in enumerate(image_urls):
                try:
                    if url.startswith("data:image"):
                        base64_data = url.split(",", 1)[1]
                        img_bytes = base64.b64decode(base64_data)
                        await bot.send(event, MessageSegment.image(file=img_bytes))
                        logger.info(f"已发送工具图片 [{i}], 大小: {len(img_bytes)} bytes")
                    elif url.startswith("http://") or url.startswith("https://"):
                        from hoshino.sres import Res
                        img_seg = await Res.image_from_url(url)
                        await bot.send(event, img_seg)
                        logger.info(f"已发送工具图片 [{i}], URL: {url[:50]}...")
                except Exception as e:
                    logger.exception(f"发送工具图片失败 [{i}]: {e}")
                    
        except Exception as e:
            logger.warning(f"处理工具图片失败: {e}")
    
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
            bot, event, display_response,
            enable_markdown=conf.enable_markdown_render,
            markdown_min_length=conf.markdown_min_length
        )
    except Exception as e:
        logger.error(truncate_log(str(display_response)))
        logger.error(f"发送AI回复失败: {e}")
