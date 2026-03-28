"""
AI 聊天处理模块
处理 AI 对话逻辑，包括图片处理和 API 调用
"""
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
from .session import session_manager
from .tools import get_available_tools, get_tool_function
from .tools.registry import get_injectable_params

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


def build_messages_for_api(
    session: Any,
    persona: Optional[str],
    choice_mode: bool,
    guideline: Optional[str]
) -> List[Dict[str, Any]]:
    """
    构建用于 API 的消息列表（图片列表提示词附加到最后一条 user message）
    
    Args:
        session: Session 对象
        persona: 人格设定
        choice_mode: 是否开启选项模式
        guideline: 选项生成指导标准
        
    Returns:
        构建好的消息列表
    """
    from .session import Session
    
    messages: List[Dict[str, Any]] = []
    
    # 获取图片列表提示词
    image_list_prompt = session.build_image_list_prompt()
    
    # 构建 system content（仅包含人格和选项模式，不包含图片列表）
    system_content = ""
    
    # 添加人格设定
    if persona:
        system_content = persona
    
    # 添加选项模式提示词（如果需要）
    if choice_mode:
        guideline_section = f"\n选项生成指导标准：{guideline}\n请根据以上指导标准生成合适的选项。" if guideline else ""
        choice_prompt = CHOICE_MODE_PROMPT_TEMPLATE.format(guideline_section=guideline_section)
        if system_content:
            system_content += "\n\n" + choice_prompt
        else:
            system_content = choice_prompt
    
    # 添加 system message
    if system_content:
        messages.append({"role": "system", "content": system_content})
    
    # 添加其他消息（跳过原来的 system message）
    for msg in session.messages:
        if msg.get("role") != "system":
            messages.append(msg)
    
    # 将图片列表提示词附加到最后一条 user message
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

    # 构建精简版 payload 用于日志（messages 只保留最后 2 条）
    MAX_LOG_MESSAGES = 2
    total_msgs = len(payload["messages"])
    if total_msgs > MAX_LOG_MESSAGES:
        log_messages = [{"role": "system", "content": f"...[省略 {total_msgs - MAX_LOG_MESSAGES} 条历史消息]..."}] + payload["messages"][-MAX_LOG_MESSAGES:]
    else:
        log_messages = payload["messages"]
    
    log_payload = {
        "model": payload["model"],
        "messages": log_messages,
    }
    if "max_tokens" in payload:
        log_payload["max_tokens"] = payload["max_tokens"]
    if "temperature" in payload:
        log_payload["temperature"] = payload["temperature"]
    if "tools" in payload:
        log_payload["tools"] = [t.get("function", {}).get("name") for t in payload["tools"]]
    if "tool_choice" in payload:
        log_payload["tool_choice"] = payload["tool_choice"]
    
    logger.info(f"调用 AI API: URL={url}, Payload: {log_json(truncate_log(log_payload))}")
    
    # debug 模式：每条消息单独打印
    logger.debug(f"API 请求详情 - model: {payload['model']}, messages: {len(payload['messages'])} 条")
    for i, msg in enumerate(payload["messages"]):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            # 多模态消息，提取文本部分
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
            content_str = " | ".join(texts) if texts else "[multimodal content]"
        else:
            content_str = str(content)
        logger.debug(f"  [{i}] {role}: {truncate_log(content_str, 300, 100, 100)}")

    try:
        resp = await aiohttpx.post(url, headers=headers, json=payload)
        if not resp.ok:
            error_text = truncate_log(resp.text) if hasattr(resp, 'text') else 'unknown'
            logger.error(f"AI API 调用失败: {resp.status_code}, 响应: {error_text}")
            return {"error": f"HTTP {resp.status_code}", "content": None}

        result = resp.json
        if not result:
            logger.error("AI API 返回空结果")
            return {"error": "返回空结果", "content": None}

        logger.info(f"AI API 响应: {log_json(result)}")

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
        logger.error(f"AI API 返回错误: {error_msg}, 完整响应: {log_json(result)}")
        return {"error": error_msg, "content": None}
        
    except Exception as e:
        logger.exception(f"调用 AI API 异常: {e}")
        return {"error": str(e), "content": None}


async def execute_tool_call(
    tool_call: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    执行单个工具调用 - 支持基于类型注解的参数注入
    
    工具返回格式要求：
    {
        "success": bool,
        "content": str,        # 给 AI 看的描述
        "images": List[str],   # 真实图片列表
        "error": Optional[str],
        "metadata": Dict
    }
    
    参数注入：
        如果工具函数的参数类型注解为 Session、Bot 或 Event，
        且 AI 未提供该参数，则自动注入对应的对象
    """
    
    tool_id = tool_call.get("id", "")
    function_info = tool_call.get("function", {})
    function_name = function_info.get("name", "")
    arguments_str = function_info.get("arguments", "{}")
    
    logger.info(f"执行工具: {function_name}, args: {truncate_log(arguments_str)}")
    
    # 解析参数
    try:
        arguments = json.loads(arguments_str)
    except json.JSONDecodeError:
        logger.error(f"工具参数解析失败: {arguments_str}")
        return {
            "tool_call_id": tool_id,
            "role": "tool",
            "content": json.dumps({"success": False, "error": "参数解析失败"}, ensure_ascii=False),
            "_image_urls": []
        }
    
    # 获取工具函数
    tool_func = get_tool_function(function_name)
    if not tool_func:
        logger.error(f"未找到工具: {function_name}")
        return {
            "tool_call_id": tool_id,
            "role": "tool",
            "content": json.dumps({"success": False, "error": f"未知工具: {function_name}"}, ensure_ascii=False),
            "_image_urls": []
        }
    
    # 基于类型注解注入参数（统一从 context 获取）
    if context:
        injectable = get_injectable_params(tool_func)
        for param_name, type_name in injectable.items():
            if param_name in arguments:
                continue  # AI 已提供，跳过
            
            if type_name == 'Session':
                arguments[param_name] = context.get('session')
                logger.debug(f"注入 Session 到参数 '{param_name}'")
            elif type_name == 'Bot':
                arguments[param_name] = context.get('bot')
                logger.debug(f"注入 Bot 到参数 '{param_name}'")
            elif type_name == 'Event':
                arguments[param_name] = context.get('event')
                logger.debug(f"注入 Event 到参数 '{param_name}'")
    
    # 执行工具
    try:
        result = await tool_func(**arguments)
        
        # 提取标准化字段
        success = result.get("success", False)
        content = result.get("content", "")
        images = result.get("images", [])
        error = result.get("error")
        metadata = result.get("metadata", {})
        
        # content 截断：防止 token 超限
        # 将 base64 数据截断为提示，保留占位符
        if "data:image" in content:
            pattern = r'data:image/[^;]+;base64,[A-Za-z0-9+/=]{100,}'
            content = re.sub(
                pattern,
                lambda m: m.group(0)[:50] + "...[图片数据已省略]",
                content
            )
        
        # 构造返回给 AI 的内容（包含 metadata 如占位符）
        content_for_ai = {
            "success": success,
            "content": content,
            "error": error
        }
        # 如果有 metadata（如占位符），也传给 AI
        if metadata:
            content_for_ai["metadata"] = metadata
        
        # 构造返回
        return {
            "tool_call_id": tool_id,
            "role": "tool",
            "content": json.dumps(content_for_ai, ensure_ascii=False),
            "_image_urls": images  # 真实图片，直接用于发送
        }
        
    except Exception as e:
        logger.exception(f"工具执行失败: {e}")
        return {
            "tool_call_id": tool_id,
            "role": "tool",
            "content": json.dumps({"success": False, "error": str(e)}, ensure_ascii=False),
            "_image_urls": []
        }


async def call_ai_api_with_tools(
    messages: List[Dict[str, Any]], 
    api_config: Dict[str, Any],
    max_tool_rounds: int = 5,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    调用 AI API 并处理 Tool Calling（支持多轮工具调用）
    
    Args:
        messages: 消息列表
        api_config: API 配置
        max_tool_rounds: 最大工具调用轮数，防止无限循环
        context: 工具调用上下文，包含 session、bot、event 等可注入对象
    
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
            tool_result = await execute_tool_call(tool_call, context=context)
            all_tool_results.append({
                "tool_call": tool_call,
                "result": tool_result
            })
            current_messages.append(tool_result)
            logger.info(f"工具调用结果: {truncate_log(tool_result['content'])}")
        
        # 工具调用后，如果有生成图片，添加系统提示让 AI 知道可用标识符
        if context and context.get('session'):
            session = context.get('session')
            image_list_prompt = session.build_image_list_prompt()
            if image_list_prompt:
                current_messages.append({
                    "role": "system",
                    "content": image_list_prompt
                })
                logger.debug("已添加图片列表系统提示到对话")
    
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
    
    # 提前获取 persona 和 session，确保图片存储和后续使用同一个 session 对象
    persona = persona_manager.get_persona(user_id, group_id)
    session = session_manager.get_session(user_id, group_id, persona)
    
    # 处理图片上传（无论模型是否支持多模态，都存储图片供工具使用）
    if image_urls and not supports_multimodal:
        # 模型不支持多模态，但有图片
        # 存储图片到 session，用户可以通过工具（如 edit_image）使用
        for img_url in image_urls:
            base64_image = await download_image_to_base64(img_url)
            if base64_image:
                identifier = session.store_user_image(base64_image)
                logger.info(f"存储用户图片: {identifier} (模型不支持多模态，可通过工具使用)")
            else:
                logger.warning(f"图片处理失败，跳过: {img_url}")
        
        if user_input:
            # 有文本内容，只发送文本（content 必须是 str）
            logger.debug(f"模型 {api_config.get('model')} 不支持多模态，图片已存储，仅发送文本")
            message_content = user_input
        else:
            # 只有图片没有文本，提示用户图片已存储，可以通过工具使用
            await bot.send(event, f"图片已接收并保存。当前模型不支持直接识别图片，你可以通过工具（如 #编辑图片）来处理这些图片。")
            return
    elif image_urls and supports_multimodal:
        # 有多模态内容：图片 + 文本
        content_parts: List[Dict[str, Any]] = []
        
        for img_url in image_urls:
            base64_image = await download_image_to_base64(img_url)
            if base64_image:
                # 存储到 session 并获取标识符
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

    # 添加用户消息到 session
    session.add_message("user", message_content)

    # 构建用于 API 的消息列表（包含图片列表提示词）
    messages_for_api = build_messages_for_api(
        session, persona, choice_mode_enabled and in_continuous_mode, choice_guideline
    )

    # 调用 AI API（支持 Tool Calling）
    # 构建工具调用上下文（包含所有可注入对象）
    tool_context = {
        "session": session,
        "bot": bot,
        "event": event,
    }
    api_result = await call_ai_api_with_tools(
        messages_for_api, 
        api_config, 
        context=tool_context,
    )
    
    # 发送工具生成的图片（如果有）
    # 工具返回标准化格式：images 字段包含真实图片数据
    for tool_result in api_result.get("tool_results", []):
        try:
            image_urls = tool_result["result"].get("_image_urls", [])
            
            for i, url in enumerate(image_urls):
                try:
                    if url.startswith("data:image"):
                        # Base64 图片：直接解码发送
                        # 注意：图片已在工具内部存储，这里只负责发送
                        base64_data = url.split(",", 1)[1]
                        img_bytes = base64.b64decode(base64_data)
                        await bot.send(event, MessageSegment.image(file=img_bytes))
                        logger.info(f"已发送工具图片 [{i}], 大小: {len(img_bytes)} bytes")
                    elif url.startswith("http://") or url.startswith("https://"):
                        # HTTP URL：下载后发送
                        from hoshino.sres import Res
                        img_seg = await Res.image_from_url(url)
                        await bot.send(event, img_seg)
                        logger.info(f"已发送工具图片 [{i}], URL: {url[:50]}...")
                except Exception as e:
                    logger.exception(f"发送工具图片失败 [{i}]: {e}")
                    
        except Exception as e:
            logger.warning(f"处理工具图片失败: {e}")
    
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
        logger.error(truncate_log(str(display_response)))
        logger.error(f"发送AI回复失败: {e}")
