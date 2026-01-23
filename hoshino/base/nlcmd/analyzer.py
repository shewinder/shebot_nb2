"""
LLM意图分析器
调用LLM分析用户消息意图，返回应该触发的命令
"""
import json
from typing import Dict, Optional, List
from loguru import logger

import nonebot
import aiohttp

from nonebot import get_plugin_config
from .config import Config
from .collector import CommandInfo

# 加载配置
conf = get_plugin_config(Config)


async def analyze_intent(user_message: str, available_commands: List[CommandInfo]) -> Optional[Dict]:
    """分析用户消息意图，返回应该触发的命令"""
    if not conf.api_key:
        logger.warning("NLCMD API密钥未配置")
        return None
    if not available_commands:
        logger.warning("没有可用的命令列表")
        return None
    commands_text = "\n".join([f"{i+1}. {c.plugin} {c.cmds} {c.shell_command_help}" for i, c in enumerate(available_commands[:200])])
    driver = nonebot.get_driver()
    command_prefix = driver.config.command_start
    sep = list(command_prefix)[0]
    # 构建系统提示词
    system_prompt = """你是一个智能命令助手，负责将用户的自然语言请求转换为精确的机器人“可触发消息”(virtual message)，用于触发 NoneBot 的 matcher。

可用命令列表：
{commands}

请分析用户的消息，从上述命令列表中选择最合适的触发方式，并返回 JSON：
{{
    "command_msg": "你构造出的 command_msg（会被作为 event.message 重新投递）",
    "command": "你选择的命令/触发器名称（若无法给出可留空字符串）",
    "confidence": 0.0-1.0的置信度分数
}}

规则：
1. 你的输出将被直接写入 event.message 并重新投递，所以 command_msg 必须是“用户实际会发的那句话/那条命令”。\n+2. 若 matcher 的 triggers.commands 非空，优先用命令触发：command_msg 建议形如 “/命令 参数…”。\n+3. 若 triggers.shell_commands 非空，可用 shell 命令触发：command_msg 形如 “/命令 参数…”（具体取决于该 bot 的命令前缀）。\n+4. 若无法确定，请将 confidence 设为 < 0.5。\n+5. 只返回 JSON，不要夹带任何解释文字。\n+6. **重要：如果用户输入的消息已经精确匹配了可用命令列表中的某个命令（包括命令前缀和命令名完全一致），请返回 {{"skip": true}}，表示该消息已经精确匹配命令，不需要 nlcmd 处理。**

示例：
用户: "帮我开启解析功能"
返回: {{"command_msg": "{sep}开启解析", "command": "开启解析", "confidence": 0.9}}


用户: "你好"
返回: {{"command_msg": "你好", "command": "你好", "confidence": 0.3}}""".format(commands=commands_text, sep=sep)
    
    # 构建请求
    url = f"{conf.api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {conf.api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": conf.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "max_tokens": conf.max_tokens,
        "temperature": conf.temperature
        # 注意：某些API可能不支持response_format，如果支持可以添加：
        # "response_format": {"type": "json_object"}
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, ssl=False) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    logger.error(f"NLCMD API调用失败: {resp.status}, 响应: {text}")
                    return None
                
                result = await resp.json()
                if not result:
                    logger.error("NLCMD API返回空结果")
                    return None
                
                if "choices" in result and len(result["choices"]) > 0:
                    message = result["choices"][0].get("message", {})
                    if "content" in message:
                        content = message["content"]
                        try:
                            # 解析JSON响应
                            intent = json.loads(content)
                            
                            # 验证必要字段
                            if "command_msg" not in intent:
                                logger.error(f"LLM返回格式错误，缺少command_msg字段: {intent}")
                                return None
                            
                            # 设置默认值
                            intent.setdefault("command", intent.get("command_msg", ""))
                            intent.setdefault("confidence", 0.5)
                            
                            # 确保confidence是数字
                            try:
                                intent["confidence"] = float(intent["confidence"])
                            except (ValueError, TypeError):
                                intent["confidence"] = 0.5
                            
                            return intent
                        except json.JSONDecodeError as e:
                            logger.error(f"解析LLM返回的JSON失败: {e}, 内容: {content}")
                            # 尝试从文本中提取JSON
                            try:
                                # 查找JSON对象
                                import re
                                json_match = re.search(r'\{[^}]+\}', content)
                                if json_match:
                                    intent = json.loads(json_match.group())
                                    intent.setdefault("command_msg", intent.get("command", ""))
                                    intent.setdefault("confidence", 0.5)
                                    return intent
                            except:
                                pass
                            return None
                    else:
                        logger.error(f"NLCMD API返回格式错误，缺少content字段: {result}")
                        return None
                else:
                    error_info = result.get("error", {})
                    error_msg = error_info.get("message", "未知错误") if error_info else "返回格式错误"
                    logger.error(f"NLCMD API返回错误: {error_msg}, 完整响应: {result}")
                    return None
    except Exception as e:
        logger.exception(f"调用NLCMD API异常: {e}")
        return None
