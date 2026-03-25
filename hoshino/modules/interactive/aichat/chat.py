"""
AI 聊天处理模块
处理 AI 对话逻辑，包括图片处理和 API 调用
"""
import base64
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from loguru import logger

from io import BytesIO

from hoshino import Bot, Event, MessageSegment
from hoshino.util import aiohttpx, get_event_imageurl
from hoshino.util.message_util import extract_images_from_reply

from .api import api_manager
from .config import Config
from .md_render import render_text_if_markdown, strip_thinking_tags, MD_IMAGE_PATTERN
from .persona import persona_manager
from .session import session_manager
from .tools import get_available_tools, get_tool_function

# 加载配置
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
    """
    从 AI 回复中解析选项
    
    Returns:
        (正文内容, {1: "选项1", 2: "选项2", 3: "选项3"})
    """
    choices_dict = {}
    
    # 查找 [CHOICES]...[/CHOICES] 标记
    match = CHOICES_PATTERN.search(response)
    if not match:
        return response.strip(), choices_dict
    
    choices_text = match.group(1).strip()
    
    # 解析选项行
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
    
    # 移除 [CHOICES] 标记，保留正文
    content = CHOICES_PATTERN.sub('', response).strip()
    
    return content, choices_dict


def format_choices_for_display(choices: Dict[int, str]) -> str:
    """格式化选项为易读格式"""
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
    """
    构建带选项模式提示词的消息列表
    
    Args:
        session_messages: 原始 session 消息列表
        original_persona: 原始人格
        guideline: 选项生成指导标准
        
    Returns:
        修改后的消息列表
    """
    messages = []
    
    # 构建 system message
    system_content = ""
    
    # 先添加原始人格（如果有）
    if original_persona:
        system_content = original_persona
    
    # 添加选项生成提示词
    guideline_section = f"\n选项生成指导标准：{guideline}\n请根据以上指导标准生成合适的选项。" if guideline else ""
    choice_prompt = CHOICE_MODE_PROMPT_TEMPLATE.format(guideline_section=guideline_section)
    
    if system_content:
        system_content += "\n\n" + choice_prompt
    else:
        system_content = choice_prompt
    
    messages.append({"role": "system", "content": system_content})
    
    # 添加其他消息（跳过原来的 system message）
    for msg in session_messages:
        if msg.get("role") != "system":
            messages.append(msg)
    
    return messages


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


async def call_ai_api(
    messages: List[Dict[str, Any]], 
    api_config: Dict[str, Any],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None
) -> Dict[str, Any]:
    """
    调用 AI API，支持 Tool/Function Calling
    
    Returns:
        {
            "content": str,  # AI 回复文本
            "reasoning_content": str,  # 推理内容
            "tool_calls": List[Dict],  # 工具调用请求
            "finish_reason": str,  # 结束原因
            "raw_response": Dict,  # 原始响应
        }
    """
    if not api_config or not api_config.get("api_key"):
        logger.warning("AI API 未配置或密钥为空")
        return {"error": "API 未配置", "content": None}

    if not messages:
        logger.error("消息列表为空")
        return {"error": "消息列表为空", "content": None}

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
    
    # 添加 tools 参数（如果模型支持且提供了 tools）
    if tools and api_config.get("supports_tools", False):
        payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        logger.debug(f"启用 Tool Calling，工具数量: {len(tools)}")

    logger.debug(f"调用 AI API: URL={url}, Payload: {payload}")

    try:
        resp = await aiohttpx.post(url, headers=headers, json=payload)
        if not resp.ok:
            logger.error(f"AI API 调用失败: {resp.status_code}, 响应: {resp.text}")
            return {"error": f"HTTP {resp.status_code}", "content": None}

        result = resp.json
        if not result:
            logger.error("AI API 返回空结果")
            return {"error": "返回空结果", "content": None}

        logger.info(f"AI API 响应: {str(result)}")

        if "choices" in result and len(result["choices"]) > 0:
            choice = result["choices"][0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "")
            
            content = message.get("content", "") or ""
            reasoning_content = message.get("reasoning_content", "") or ""
            tool_calls = message.get("tool_calls", [])
            
            return {
                "content": content.strip() if content else None,
                "reasoning_content": reasoning_content.strip() if reasoning_content else None,
                "tool_calls": tool_calls if tool_calls else [],
                "finish_reason": finish_reason,
                "raw_response": result,
            }
        
        error_info = result.get("error", {})
        error_msg = error_info.get("message", "未知错误") if error_info else "返回格式错误"
        logger.error(f"AI API 返回错误: {error_msg}, 完整响应: {result}")
        return {"error": error_msg, "content": None}
        
    except Exception as e:
        logger.exception(f"调用 AI API 异常: {e}")
        return {"error": str(e), "content": None}


async def execute_tool_call(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行单个工具调用
    
    Args:
        tool_call: {
            "id": str,
            "type": "function",
            "function": {
                "name": str,
                "arguments": str (JSON)
            }
        }
    
    Returns:
        {
            "tool_call_id": str,
            "role": "tool",
            "content": str (JSON)
        }
    """
    import json
    
    tool_id = tool_call.get("id", "")
    function_info = tool_call.get("function", {})
    function_name = function_info.get("name", "")
    arguments_str = function_info.get("arguments", "{}")
    
    logger.info(f"执行工具调用: {function_name}, args: {arguments_str}")
    
    # 解析参数
    try:
        arguments = json.loads(arguments_str)
    except json.JSONDecodeError:
        logger.error(f"工具参数解析失败: {arguments_str}")
        return {
            "tool_call_id": tool_id,
            "role": "tool",
            "content": json.dumps({"error": "参数解析失败"})
        }
    
    # 获取工具函数
    tool_func = get_tool_function(function_name)
    if not tool_func:
        logger.error(f"未找到工具函数: {function_name}")
        return {
            "tool_call_id": tool_id,
            "role": "tool",
            "content": json.dumps({"error": f"未知工具: {function_name}"})
        }
    
    # 执行工具
    try:
        result = await tool_func(**arguments)
        return {
            "tool_call_id": tool_id,
            "role": "tool",
            "content": json.dumps(result, ensure_ascii=False)
        }
    except Exception as e:
        logger.exception(f"工具执行失败: {e}")
        return {
            "tool_call_id": tool_id,
            "role": "tool",
            "content": json.dumps({"error": str(e)})
        }


async def call_ai_api_with_tools(
    messages: List[Dict[str, Any]], 
    api_config: Dict[str, Any],
    max_tool_rounds: int = 5
) -> Dict[str, Any]:
    """
    调用 AI API 并处理 Tool Calling（支持多轮工具调用）
    
    Args:
        messages: 消息列表
        api_config: API 配置
        max_tool_rounds: 最大工具调用轮数，防止无限循环
    
    Returns:
        {
            "content": str,  # 最终回复文本
            "tool_results": List[Dict],  # 所有工具调用结果
            "error": str,  # 错误信息
        }
    """
    if not api_config.get("supports_tools", False):
        # 不支持 tools，直接调用普通 API
        result = await call_ai_api(messages, api_config, tools=None)
        return {
            "content": result.get("content") or result.get("reasoning_content"),
            "tool_results": [],
            "error": result.get("error")
        }
    
    tools = get_available_tools()
    current_messages = messages.copy()
    all_tool_results = []
    
    for round_num in range(max_tool_rounds):
        logger.debug(f"Tool calling 第 {round_num + 1} 轮")
        
        # 调用 API
        result = await call_ai_api(current_messages, api_config, tools=tools)
        
        if result.get("error"):
            return {"content": None, "tool_results": all_tool_results, "error": result["error"]}
        
        # 检查是否有工具调用
        tool_calls = result.get("tool_calls", [])
        if not tool_calls:
            # 没有工具调用，返回最终回复
            content = result.get("content")
            if not content and result.get("reasoning_content"):
                content = result.get("reasoning_content")
            return {
                "content": content,
                "tool_results": all_tool_results,
                "error": None
            }
        
        # 有工具调用，添加 assistant 消息到对话
        assistant_message = result.get("raw_response", {}).get("choices", [{}])[0].get("message", {})
        current_messages.append(assistant_message)
        
        # 执行所有工具调用
        for tool_call in tool_calls:
            tool_result = await execute_tool_call(tool_call)
            all_tool_results.append({
                "tool_call": tool_call,
                "result": tool_result
            })
            current_messages.append(tool_result)
            logger.info(f"工具调用结果: {tool_result['content'][:200]}...")
    
    # 达到最大轮数限制
    logger.warning(f"达到最大工具调用轮数限制: {max_tool_rounds}")
    return {
        "content": "工具调用次数过多，请简化请求",
        "tool_results": all_tool_results,
        "error": "达到最大工具调用轮数限制"
    }


# 保留旧函数以兼容代码，但实际使用 call_ai_api_with_tools
async def call_ai_api_legacy(messages: List[Dict[str, Any]], api_config: Dict[str, Any]) -> Optional[str]:
    """旧版 API 调用（兼容用）"""
    result = await call_ai_api(messages, api_config, tools=None)
    return result.get("content") or result.get("reasoning_content")


async def handle_ai_chat(bot: Bot, event: Event):
    """处理AI聊天消息（支持图片多模态和选项模式）"""
    # 获取消息内容
    msg = str(event.message).strip()
    
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    # 检查是否以#开头，或者处于连续对话模式
    in_continuous_mode = session_manager.is_continuous_mode(user_id, group_id)
    
    # 获取选项模式状态
    choice_mode_enabled, choice_guideline = session_manager.get_choice_mode(user_id, group_id)
    last_choices = session_manager.get_last_choices(user_id, group_id)
    
    if msg.startswith('#'):
        # 移除#前缀
        user_input = msg[1:].strip()
    elif in_continuous_mode:
        # 连续对话模式，无需#前缀
        user_input = msg
    else:
        # 非连续对话模式且不以#开头，忽略
        return
    
    # 检查是否发送了数字选项（仅在选项模式下）
    if choice_mode_enabled and last_choices:
        # 检查是否为纯数字 1/2/3
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

    # 如果开启了选项模式，构建带提示词的消息列表
    if choice_mode_enabled and in_continuous_mode:
        messages_for_api = build_messages_with_choice_mode(
            session.messages, persona, choice_guideline
        )
    else:
        messages_for_api = session.messages

    # 调用 AI API（支持 Tool Calling）
    api_result = await call_ai_api_with_tools(messages_for_api, api_config)
    
    if api_result.get("error") and not api_result.get("content"):
        await bot.send(event, f"AI服务暂时不可用，请稍后再试\n错误: {api_result['error']}")
        # 移除刚才添加的用户消息
        if session.messages and session.messages[-1].get("role") == "user":
            session.messages.pop()
        return
    
    response = api_result.get("content", "")
    
    # 注意：工具结果已包含在对话历史中传给模型
    # 模型应在最终回复中组织好工具结果的呈现方式
    # 下面的代码统一处理最终回复的发送（Markdown 渲染或提取图片 URL）
    
    # 解析选项（如果开启了选项模式）
    display_response = response
    if choice_mode_enabled and in_continuous_mode:
        content, choices = parse_choices_from_response(response)
        if choices:
            # 存储选项到 session
            session_manager.set_last_choices(user_id, group_id, choices)
            # 构建显示内容（正文 + 格式化选项）
            display_response = content + format_choices_for_display(choices)
            # 将解析后的内容（不含选项标记）添加到历史
            session.add_message("assistant", content)
        else:
            # 没有解析到选项，清空上一次的选项
            session_manager.set_last_choices(user_id, group_id, {})
            session.add_message("assistant", response)
    else:
        session.add_message("assistant", response)
    
    # 发送回复
    sent = False
    try:
        if not display_response:
            await bot.send(event, "抱歉，我没有生成任何内容，请重试")
            return
        
        # 策略：优先尝试 Markdown 渲染（包含图片链接的文本）
        # 如果渲染成功，发送渲染后的图片
        # 如果渲染失败或未启用，再提取 URL 单独发送图片和文本
        should_render = (
            conf.enable_markdown_render and
            len(display_response) >= conf.markdown_min_length
        )
        
        if should_render:
            try:
                img_bytes = await render_text_if_markdown(
                    display_response,
                    min_length=conf.markdown_min_length
                )
                if img_bytes:
                    await bot.send(event, MessageSegment.image(BytesIO(img_bytes)))
                    sent = True
                    logger.info("Markdown 渲染成功，发送渲染后的图片")
            except Exception as render_err:
                logger.warning(f"Markdown 渲染失败: {render_err}")
        
        if not sent:
            # Markdown 未启用、不满足条件或渲染失败
            # 提取消息中的图片 URL 并发送
            from .md_render import extract_image_urls
            image_urls = extract_image_urls(display_response)
            
            if image_urls:
                # 有图片 URL，先发送图片
                for url in image_urls:
                    try:
                        await bot.send(event, MessageSegment.image(url))
                    except Exception as img_err:
                        logger.error(f"发送图片失败: {url}, 错误: {img_err}")
                
                # 发送文本（去掉 Markdown 图片语法后的内容）
                text_content = MD_IMAGE_PATTERN.sub('', display_response)
                text_content = text_content.strip()
                
                if text_content:
                    await bot.send(event, text_content)
                sent = True
            else:
                # 没有图片 URL，直接发送文本
                await bot.send(event, display_response)
                sent = True
            
    except Exception as e:
        logger.error(str(display_response))
        logger.error(f"发送AI回复失败: {e}")
