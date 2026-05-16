"""ChatExecutor - AI API 调用与工具执行编排

从 Session 中分离出来，负责：
- 调用 AI API（单次 + 多轮工具调用）
- 工具执行调度
- 将结果写回 Session
"""
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

from .config import Config
from .tools import get_tool_function, get_available_tools
from .tools.registry import get_injectable_params
from hoshino.util import aiohttpx, log_json, truncate_log

if TYPE_CHECKING:
    from .session import Session

conf = Config.get_instance('aichat')


@dataclass
class ChatResult:
    """聊天结果数据类"""
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    usage: Optional[Dict[str, int]] = None


class ChatExecutor:
    """AI 对话执行器，编排 API 调用和工具执行"""

    def __init__(self, session: "Session"):
        self.session = session

    async def chat(
        self,
        api_config: Dict[str, Any],
        bot: Optional[Any] = None,
        event: Optional[Any] = None,
        on_content: Optional[Callable[[str], Any]] = None,
    ) -> "ChatResult":
        """执行对话调用，自动处理消息构建和工具获取"""
        messages = await self.session._build_messages_for_chat(event)

        tools = None
        if api_config.get("supports_tools", False):
            tools = await get_available_tools(session=self.session)

        chat_context: Dict[str, Any] = {'session': self.session}
        if bot:
            chat_context['bot'] = bot
        if event:
            chat_context['event'] = event

        result = await self._chat_with_api(
            messages=messages,
            api_config=api_config,
            tools=tools,
            context=chat_context,
            on_content=on_content,
        )

        if result.usage:
            prompt_tokens = result.usage.get("prompt_tokens", 0) or 0
            completion_tokens = result.usage.get("completion_tokens", 0) or 0
            if prompt_tokens > 0 or completion_tokens > 0:
                self.session.add_tokens(prompt_tokens, completion_tokens)

        return result

    async def _call_ai_api(
        self,
        messages: List[Dict[str, Any]],
        api_config: Dict[str, Any],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None
    ) -> Dict[str, Any]:
        """单次 AI API 调用"""
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

        if "max_tokens" in api_config:
            payload["max_tokens"] = api_config["max_tokens"]
        if "temperature" in api_config:
            payload["temperature"] = api_config["temperature"]

        if tools and api_config.get("supports_tools", False):
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice
            logger.debug(f"启用 Tool Calling，工具数量: {len(tools)}")

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
            log_payload["tools_count"] = len(payload["tools"])
        if "tool_choice" in payload:
            log_payload["tool_choice"] = payload["tool_choice"]

        logger.info(f"调用 AI API: URL={url}, Payload: {log_json(truncate_log(log_payload))}")

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
                usage = result.get("usage", {})

                return {
                    "content": content.strip() if content else None,
                    "reasoning_content": reasoning_content.strip() if reasoning_content else None,
                    "tool_calls": tool_calls if tool_calls else [],
                    "finish_reason": finish_reason,
                    "raw_response": result,
                    "usage": usage if usage else None,
                }

            error_info = result.get("error", {})
            error_msg = error_info.get("message", "未知错误") if error_info else "返回格式错误"
            logger.error(f"AI API 返回错误: {error_msg}, 完整响应: {log_json(result)}")
            return {"error": error_msg, "content": None}

        except Exception as e:
            logger.exception(f"调用 AI API 异常: {e}")
            return {"error": str(e), "content": None}

    async def _execute_tool_call(
        self,
        tool_call: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行单个工具调用"""
        tool_id = tool_call.get("id", "")
        function_info = tool_call.get("function", {})
        function_name = function_info.get("name", "")
        arguments_str = function_info.get("arguments", "{}")

        logger.info(f"执行工具: {function_name}, args: {truncate_log(arguments_str)}")

        try:
            arguments = json.loads(arguments_str)
        except json.JSONDecodeError:
            logger.error(f"工具参数解析失败: {arguments_str}")
            return {
                "tool_call_id": tool_id,
                "role": "tool",
                "content": json.dumps({"success": False, "error": "参数解析失败"}, ensure_ascii=False),
            }

        tool_func = get_tool_function(function_name)
        if not tool_func:
            logger.error(f"未找到工具: {function_name}")
            return {
                "tool_call_id": tool_id,
                "role": "tool",
                "content": json.dumps({"success": False, "error": f"未知工具: {function_name}"}, ensure_ascii=False),
            }

        if context:
            injectable = get_injectable_params(tool_func)
            for param_name, type_name in injectable.items():
                if param_name in arguments:
                    continue
                if type_name == 'Session':
                    arguments[param_name] = context.get('session')
                elif type_name == 'Bot':
                    arguments[param_name] = context.get('bot')
                elif type_name == 'Event':
                    arguments[param_name] = context.get('event')

        try:
            result = await tool_func(**arguments)

            success = result.get("success", False)
            content = result.get("content", "")
            error = result.get("error")
            metadata = result.get("metadata", {})

            # MCP 图像自动管道
            images = result.get("images", [])
            if images:
                identifiers = []
                for img in images:
                    if isinstance(img, str) and img.startswith("data:"):
                        try:
                            identifier = await self.session.store_ai_image(img)
                            identifiers.append(identifier)
                        except Exception:
                            logger.exception(f"自动存储 MCP 图像失败")
                if identifiers:
                    content = content + "\n" + " ".join(identifiers)

            # 简化日志中的 base64 图片数据
            if "data:image" in content:
                import re
                pattern = r'data:image/[^;]+;base64,[A-Za-z0-9+/=]{100,}'
                content = re.sub(
                    pattern,
                    lambda m: m.group(0)[:50] + "...[图片数据已省略]",
                    content
                )

            content_for_ai = {
                "success": success,
                "content": content,
                "error": error
            }
            if metadata:
                content_for_ai["metadata"] = metadata

            return {
                "tool_call_id": tool_id,
                "role": "tool",
                "content": json.dumps(content_for_ai, ensure_ascii=False),
            }

        except Exception as e:
            logger.exception(f"工具执行失败: {e}")
            return {
                "tool_call_id": tool_id,
                "role": "tool",
                "content": json.dumps({"success": False, "error": str(e)}, ensure_ascii=False),
            }

    async def _chat_with_api(
        self,
        messages: List[Dict[str, Any]],
        api_config: Dict[str, Any],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tool_rounds: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        on_content: Optional[Callable[[str], Any]] = None,
    ) -> "ChatResult":
        """与 AI API 进行对话，支持多轮工具调用"""
        if max_tool_rounds is None:
            max_tool_rounds = conf.max_tool_rounds

        if not tools or not api_config.get("supports_tools", False):
            result = await self._call_ai_api(messages, api_config, tools=None)
            return ChatResult(
                content=result.get("content"),
                reasoning_content=result.get("reasoning_content"),
                error=result.get("error"),
                usage=result.get("usage"),
            )

        current_messages = messages.copy()
        all_tool_results = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        for round_num in range(max_tool_rounds):
            logger.debug(f"Tool calling 第 {round_num + 1} 轮")

            if round_num > 0 and api_config.get("supports_tools", False):
                tools = await get_available_tools(session=self.session)
                logger.debug(f"[MCP] 第 {round_num + 1} 轮重新获取工具，共 {len(tools) if tools else 0} 个")

            result = await self._call_ai_api(current_messages, api_config, tools=tools)

            usage = result.get("usage")
            if usage and isinstance(usage, dict):
                total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0) or 0
                total_usage["completion_tokens"] += usage.get("completion_tokens", 0) or 0
                total_usage["total_tokens"] += usage.get("total_tokens", 0) or 0

            if result.get("error"):
                return ChatResult(
                    error=result["error"],
                    tool_results=all_tool_results,
                    usage=total_usage if total_usage["total_tokens"] > 0 else None,
                )

            content = result.get("content")
            tool_calls = result.get("tool_calls", [])

            if not tool_calls:
                return ChatResult(
                    content=content,
                    reasoning_content=result.get("reasoning_content"),
                    tool_results=all_tool_results,
                    usage=total_usage if total_usage["total_tokens"] > 0 else None,
                )

            if content and on_content:
                await on_content(content)

            assistant_message = result.get("raw_response", {}).get("choices", [{}])[0].get("message", {})
            current_messages.append(assistant_message)
            self.session.add_raw_message(assistant_message)

            for tool_call in tool_calls:
                tool_result = await self._execute_tool_call(tool_call, context=context)
                all_tool_results.append({
                    "tool_call": tool_call,
                    "result": tool_result
                })
                current_messages.append(tool_result)
                self.session.add_raw_message(tool_result)

                try:
                    parsed_content = json.loads(tool_result['content'])
                    metadata = parsed_content.get('metadata', {})
                    if metadata:
                        logger.info(f"工具调用 stdout:\n{metadata.get('stdout', '')}")
                        if metadata.get('stderr'):
                            logger.info(f"工具调用 stderr:\n{metadata['stderr']}")
                except Exception:
                    pass
                logger.info(f"工具调用结果: {truncate_log(tool_result['content'])}")

        logger.warning(f"达到最大工具调用轮数限制: {max_tool_rounds}")
        return ChatResult(
            content="工具调用次数过多，请简化请求",
            error="达到最大工具调用轮数限制",
            tool_results=all_tool_results,
            usage=total_usage if total_usage["total_tokens"] > 0 else None,
        )
