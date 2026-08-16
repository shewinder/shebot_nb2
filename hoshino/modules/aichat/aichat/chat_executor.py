"""ChatExecutor - AI API 调用与工具执行编排

从 Session 中分离出来，负责：
- 调用 AI API（单次 + 多轮工具调用）
- 工具执行调度
- 将结果写回 Session
"""
import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

from .config import Config
from .infra import AppError, LLMError, get_gateway, sanitize
from .infra.metrics import metrics
from .tools.access import get_available_tools, get_tool_function
from .tools.permission import check_permission, get_tool_permission
from .tools.registry import get_injectable_params, ok, fail
from hoshino.util import log_json, truncate_log

if TYPE_CHECKING:
    from .session import Session

conf = Config.get_instance('aichat')


@dataclass
class ChatResult:
    """聊天结果数据类"""
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[AppError] = None
    usage: Optional[Dict[str, int]] = None


@dataclass
class APIResponse:
    """单次 LLM API 调用的类型化结果（替代裸 dict）"""
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: str = ""
    # 从原始响应提取的完整 assistant 消息（含 tool_calls 原始结构），供写回历史
    assistant_message: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, int]] = None
    error: Optional[AppError] = None


class ChatExecutor:
    """AI 对话执行器，编排 API 调用和工具执行"""

    def __init__(self, session: "Session"):
        self.session = session

    @property
    def _tag(self) -> str:
        label = getattr(self.session, 'agent_label', 'main')
        return f"[Agent:{label}]"

    async def chat(
        self,
        api_config: Dict[str, Any],
        bot: Optional[Any] = None,
        event: Optional[Any] = None,
        on_content: Optional[Callable[[str], Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_rounds: Optional[int] = None,
    ) -> "ChatResult":
        """执行对话调用，自动处理消息构建和工具获取

        Args:
            tools: 显式指定工具列表。None=自动获取全量工具，[]=无工具
            max_rounds: 最大工具调用轮数。None=使用配置默认值
        """
        messages = await self.session._build_messages_for_chat(event)

        if tools is None and api_config.get("supports_tools", False):
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
            max_tool_rounds=max_rounds,
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
    ) -> APIResponse:
        """单次 AI API 调用（经 LLMGateway：超时/重试/脱敏）"""
        if not api_config or not api_config.get("api_key"):
            logger.warning("AI API 未配置或密钥为空")
            return APIResponse(error=AppError("API 未配置", code="llm.unconfigured"))

        if not messages:
            logger.error("消息列表为空")
            return APIResponse(error=AppError("消息列表为空", code="llm.empty_messages"))

        call_tools = tools if (tools and api_config.get("supports_tools", False)) else None
        if call_tools:
            logger.debug(f"启用 Tool Calling，工具数量: {len(call_tools)}")

        MAX_LOG_MESSAGES = 2
        total_msgs = len(messages)
        if total_msgs > MAX_LOG_MESSAGES:
            log_messages = [{"role": "system", "content": f"...[省略 {total_msgs - MAX_LOG_MESSAGES} 条历史消息]..."}] + messages[-MAX_LOG_MESSAGES:]
        else:
            log_messages = messages

        log_payload = {
            "model": api_config["model"],
            "messages": sanitize(log_messages),
        }
        if "max_tokens" in api_config:
            log_payload["max_tokens"] = api_config["max_tokens"]
        if "temperature" in api_config:
            log_payload["temperature"] = api_config["temperature"]
        if call_tools:
            log_payload["tools_count"] = len(call_tools)

        logger.info(f"{self._tag} 调用 AI API: model={api_config['model']}, Payload: {log_json(truncate_log(log_payload))}")

        gateway = get_gateway(
            api_config["api_base"],
            api_config["api_key"],
            max_retries=conf.llm_max_retries,
            connect_timeout=conf.llm_connect_timeout,
            read_timeout=conf.llm_read_timeout,
        )

        try:
            result = await gateway.chat(
                messages,
                model=api_config["model"],
                tools=call_tools,
                temperature=api_config.get("temperature"),
                max_tokens=api_config.get("max_tokens"),
            )
        except LLMError as e:
            logger.error(f"{self._tag} AI API 调用失败: {e}")
            return APIResponse(error=e)

        logger.info(f"{self._tag} AI API 响应: {log_json(sanitize(result.raw))}")

        assistant_message: Optional[Dict[str, Any]] = None
        if result.raw:
            choices = result.raw.get("choices") or []
            if choices:
                assistant_message = choices[0].get("message")

        return APIResponse(
            content=result.content,
            reasoning_content=result.reasoning_content,
            tool_calls=result.tool_calls,
            finish_reason=result.finish_reason or "",
            assistant_message=assistant_message,
            usage=result.usage,
        )

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

        logger.info(f"{self._tag} 执行工具: {function_name}, args: {truncate_log(arguments_str)}")

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

        # 执行层权限校验：防模型幻觉调用未出现在 schema 中的工具名绕过
        level = get_tool_permission(function_name)
        session = context.get('session') if context else None
        has_perm, reason = check_permission(
            level,
            user_id=getattr(session, 'user_id', None) if session else None,
            event=context.get('event') if context else None,
        )
        if not has_perm:
            logger.warning(f"{self._tag} 工具权限拒绝: {function_name} (需要 {level})")
            return {
                "tool_call_id": tool_id,
                "role": "tool",
                "content": json.dumps({"success": False, "error": reason}, ensure_ascii=False),
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

        start = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                tool_func(**arguments),
                timeout=conf.tool_timeout,
            )
        except asyncio.TimeoutError:
            metrics.record_tool_timeout()
            logger.error(f"{self._tag} 工具执行超时（>{conf.tool_timeout}s）: {function_name}")
            return {
                "tool_call_id": tool_id,
                "role": "tool",
                "content": json.dumps(
                    {"success": False, "error": f"工具执行超时: {function_name}"},
                    ensure_ascii=False,
                ),
            }
        except Exception as e:
            logger.exception(f"工具执行失败: {e}")
            return {
                "tool_call_id": tool_id,
                "role": "tool",
                "content": json.dumps({"success": False, "error": str(e)}, ensure_ascii=False),
            }
        metrics.record_tool_call((time.perf_counter() - start) * 1000)

        return await self._process_tool_result(tool_id, result)

    async def _process_tool_result(
        self,
        tool_id: str,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """整形工具返回：MCP 图片管道 + base64 脱敏 + 标准 ok/fail 结构"""
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
            pattern = r'data:image/[^;]+;base64,[A-Za-z0-9+/=]{100,}'
            content = re.sub(
                pattern,
                lambda m: m.group(0)[:50] + "...[图片数据已省略]",
                content
            )

        content_for_ai = ok(content, metadata) if success else fail(content, error=error, metadata=metadata)

        return {
            "tool_call_id": tool_id,
            "role": "tool",
            "content": json.dumps(content_for_ai, ensure_ascii=False),
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
            resp = await self._call_ai_api(messages, api_config, tools=None)
            return ChatResult(
                content=resp.content,
                reasoning_content=resp.reasoning_content,
                error=resp.error,
                usage=resp.usage,
            )

        current_messages = messages.copy()
        all_tool_results = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        for round_num in range(max_tool_rounds):
            logger.debug(f"{self._tag} Tool calling 第 {round_num + 1} 轮")

            if round_num > 0 and api_config.get("supports_tools", False) and not getattr(self.session, '_subagent_locked_tools', False):
                tools = await get_available_tools(session=self.session)
                logger.debug(f"{self._tag} [MCP] 第 {round_num + 1} 轮重新获取工具，共 {len(tools) if tools else 0} 个")

            resp = await self._call_ai_api(current_messages, api_config, tools=tools)

            if resp.usage and isinstance(resp.usage, dict):
                total_usage["prompt_tokens"] += resp.usage.get("prompt_tokens", 0) or 0
                total_usage["completion_tokens"] += resp.usage.get("completion_tokens", 0) or 0
                total_usage["total_tokens"] += resp.usage.get("total_tokens", 0) or 0

            if resp.error:
                return ChatResult(
                    error=resp.error,
                    tool_results=all_tool_results,
                    usage=total_usage if total_usage["total_tokens"] > 0 else None,
                )

            if not resp.tool_calls:
                return ChatResult(
                    content=resp.content,
                    reasoning_content=resp.reasoning_content,
                    tool_results=all_tool_results,
                    usage=total_usage if total_usage["total_tokens"] > 0 else None,
                )

            if resp.content and on_content:
                await on_content(resp.content)

            assistant_message = resp.assistant_message or {}
            current_messages.append(assistant_message)
            self.session.add_raw_message(assistant_message)

            # 并行执行所有独立工具调用
            async def _run_one(tc):
                return tc, await self._execute_tool_call(tc, context=context)

            results = await asyncio.gather(*[_run_one(tc) for tc in resp.tool_calls])

            for tool_call, tool_result in results:
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
                logger.info(f"{self._tag} 工具调用结果: {truncate_log(tool_result['content'])}")

        logger.warning(f"达到最大工具调用轮数限制: {max_tool_rounds}")
        return ChatResult(
            content="工具调用次数过多，请简化请求",
            error=AppError("达到最大工具调用轮数限制", code="agent.max_rounds"),
            tool_results=all_tool_results,
            usage=total_usage if total_usage["total_tokens"] > 0 else None,
        )
