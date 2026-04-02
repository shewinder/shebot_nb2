"""Session 管理模块"""
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from loguru import logger

from .config import Config
from .skills import skill_manager
from .tools import get_tool_function
from .tools.registry import get_injectable_params
from hoshino.util import aiohttpx, log_json, truncate_log

conf = Config.get_instance('aichat')

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


@dataclass
class ChatResult:
    """聊天结果数据类"""
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    usage: Optional[Dict[str, int]] = None


class Session:
    def __init__(self, session_id: str, persona: Optional[str] = None):
        self.session_id = session_id
        self.messages: List[Dict[str, Any]] = []
        self.last_active = time.time()
        self.continuous_mode = False
        self.choice_mode_enabled = False
        self.choice_guideline: Optional[str] = None
        self.last_choices: Dict[int, str] = {}
        self._user_images: Dict[str, str] = {}
        self._ai_images: Dict[str, str] = {}
        # SKILL 系统：已激活的 SKILL 名称集合
        self.active_skills: Set[str] = set()
        # Token 使用量统计
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_tokens: int = 0
        if persona:
            self.messages.append({"role": "system", "content": persona})
    
    def add_message(self, role: str, content: Union[str, List[Dict[str, Any]]]):
        self.messages.append({"role": role, "content": content})
        system_msg = None
        if self.messages and self.messages[0].get("role") == "system":
            system_msg = self.messages[0]
            other_messages = self.messages[1:]
        else:
            other_messages = self.messages
        
        if len(other_messages) > conf.max_history * 2:  # *2因为包含user和assistant
            other_messages = other_messages[-conf.max_history * 2:]
        
        if system_msg:
            self.messages = [system_msg] + other_messages
        else:
            self.messages = other_messages
        
        self.last_active = time.time()
    
    def store_user_image(self, image_data: str) -> str:
        identifier = f"<user_image_{len(self._user_images) + 1}>"
        self._user_images[identifier] = image_data
        self.last_active = time.time()
        
        if len(self._user_images) > 20:
            oldest = list(self._user_images.keys())[0]
            del self._user_images[oldest]
        
        return identifier
    
    def store_ai_image(self, image_data: str) -> str:
        identifier = f"<ai_image_{len(self._ai_images) + 1}>"
        self._ai_images[identifier] = image_data
        self.last_active = time.time()
        
        if len(self._ai_images) > 20:
            oldest = list(self._ai_images.keys())[0]
            del self._ai_images[oldest]
        
        return identifier
    
    def resolve_image_identifier(self, identifier: str) -> Optional[str]:
        # 兼容带尖括号和不带尖括号的格式
        # AI 有时会传入 "user_image_1" 而不是 "<user_image_1>"
        if not identifier.startswith('<'):
            identifier = f"<{identifier}>"
        
        if identifier in self._user_images:
            return self._user_images[identifier]
        
        if identifier in self._ai_images:
            return self._ai_images[identifier]
        
        return None
    
    def build_image_list_prompt(self) -> str:
        has_images = self._user_images or self._ai_images
        if not has_images:
            return ""
        
        lines = [
            "",
            "=" * 40,
            "【系统内部信息：可用图片列表】",
            "=" * 40,
            "",
            "⚠️ 严格规则（必须遵守）：",
            "1. 以下标识符仅用于调用 generate_image/edit_image 工具时的参数",
            "2. 绝对禁止在回复中输出这些标识符给用户",
            "3. 如果需要提及图片，请用文字描述（如\"刚才生成的图片\"、\"你发的第一张图\"）",
            "4. 违规输出会被系统过滤，影响回复质量",
            "",
            "可用图片标识符：",
        ]
        
        if self._user_images:
            lines.append("  用户图片：" + ", ".join(self._user_images.keys()))
        if self._ai_images:
            lines.append("  AI生成的图片：" + ", ".join(self._ai_images.keys()))

        lines.extend([
            "",
            "=" * 40,
            "【系统信息结束】",
            "=" * 40,
            ""
        ])
        
        return "\n".join(lines)
    
    def resolve_tool_image_placeholders(self, text: str) -> str:
        return text
    
    def is_expired(self) -> bool:
        if conf.session_timeout <= 0:
            return False
        return time.time() - self.last_active > conf.session_timeout
    
    # ========== SKILL 系统方法 ==========
    
    def activate_skill(self, skill_name: str) -> bool:
        """激活一个 SKILL"""
        self.active_skills.add(skill_name)
        self.last_active = time.time()
        return True
    
    def deactivate_skill(self, skill_name: str) -> bool:
        """停用指定 SKILL"""
        if skill_name in self.active_skills:
            self.active_skills.discard(skill_name)
            self.last_active = time.time()
            return True
        return False
    
    def deactivate_all_skills(self) -> None:
        """停用所有 SKILL"""
        self.active_skills.clear()
        self.last_active = time.time()
    
    def is_skill_active(self, skill_name: str) -> bool:
        """检查指定 SKILL 是否已激活"""
        return skill_name in self.active_skills
    
    def get_active_skills(self) -> Set[str]:
        """获取已激活的 SKILL 名称集合"""
        return self.active_skills.copy()
    
    def add_tokens(self, prompt_tokens: int, completion_tokens: int) -> None:
        """累加 token 使用量"""
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_tokens += prompt_tokens + completion_tokens
        self.last_active = time.time()
    
    async def build_messages(
        self,
        persona: Optional[str] = None,
        choice_mode: bool = False,
        guideline: Optional[str] = None,
        env_info: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        构建用于 API 调用的完整消息列表
        
        Args:
            persona: 人格提示词
            choice_mode: 是否启用选项生成模式
            guideline: 选项生成指导标准
            env_info: 预构建的环境信息字符串（XML格式）
        
        Returns:
            List[Dict[str, Any]]: 完整的消息列表
        """
        messages: List[Dict[str, Any]] = []
        image_list_prompt = self.build_image_list_prompt()
        
        # 构建系统消息内容
        system_content = persona or ""
        
        # 选项生成模式提示
        if choice_mode:
            guideline_section = f"\n选项生成指导标准：{guideline}\n请根据以上指导标准生成合适的选项。" if guideline else ""
            choice_prompt = CHOICE_MODE_PROMPT_TEMPLATE.format(guideline_section=guideline_section)
            system_content = f"{system_content}\n\n{choice_prompt}" if system_content else choice_prompt
        
        # 环境信息
        if env_info:
            system_content = f"{system_content}\n\n{env_info}" if system_content else env_info
        
        # 工具提示
        tool_hint = "<instructions>\n你可以调用 get_current_time 工具获取当前准确时间。\n</instructions>"
        system_content = f"{system_content}\n\n{tool_hint}" if system_content else tool_hint
        
        # SKILL 内容注入
        if conf.enable_skills:
            skill_summary = skill_manager.get_metadata_summary()
            if skill_summary:
                system_content = f"{system_content}\n\n{skill_summary}" if system_content else skill_summary
            
            skill_content = skill_manager.get_injected_content(self.session_id)
            if skill_content:
                system_content = f"{system_content}\n\n{skill_content}" if system_content else skill_content
        
        # 组装消息列表
        non_system_msgs = [msg for msg in self.messages if msg.get("role") != "system"]
        
        if system_content:
            messages.append({"role": "system", "content": system_content})
            # 同步更新 session.messages，供 web 端调试查看
            self.messages = [{"role": "system", "content": system_content}] + non_system_msgs
        else:
            self.messages = non_system_msgs
        
        messages.extend(non_system_msgs)
        
        # 追加图片列表提示到最近的用户消息
        if image_list_prompt:
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content")
                    if isinstance(content, list):
                        content.append({"type": "text", "text": image_list_prompt})
                    elif isinstance(content, str):
                        msg["content"] = content + image_list_prompt
                    break
        
        return messages
    
    # ========== 对话方法 ==========
    
    async def chat(
        self,
        api_config: Dict[str, Any],
        tools: Optional[List[Dict[str, Any]]] = None,
        on_content: Optional[Callable[[str], Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ChatResult:
        """
        执行对话调用，自动处理消息和 token 统计
        
        Args:
            api_config: API 配置
            tools: 可用工具列表
            on_content: 内容回调（用于流式输出）
            context: 上下文（用于工具注入）
        
        Returns:
            ChatResult: 对话结果
        """
        # 构建包含当前 session 的上下文
        chat_context = context.copy() if context else {}
        chat_context['session'] = self
        
        # 调用 API
        result = await self._chat_with_api(
            messages=self.messages,
            api_config=api_config,
            tools=tools,
            context=chat_context,
            on_content=on_content,
        )
        
        # 自动累加 token 使用量
        if result.usage:
            prompt_tokens = result.usage.get("prompt_tokens", 0) or 0
            completion_tokens = result.usage.get("completion_tokens", 0) or 0
            if prompt_tokens > 0 or completion_tokens > 0:
                self.add_tokens(prompt_tokens, completion_tokens)
        
        return result
    
    @classmethod
    async def chat_with_messages(
        cls,
        messages: List[Dict[str, Any]],
        api_config: Dict[str, Any],
        max_tool_rounds: int = 10,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        使用指定消息列表进行对话（非会话模式）
        
        这是一个独立的类方法，用于非交互式场景（如定时任务）调用 AI API。
        不维护会话状态，每次调用都是独立的。
        
        Args:
            messages: 消息列表
            api_config: API 配置
            max_tool_rounds: 最大工具调用轮数
            context: 可选的上下文信息
        
        Returns:
            Dict[str, Any]: 包含 content, error, tool_results, usage 等字段的结果
        """
        from .tools import get_available_tools
        
        tools = await get_available_tools() if api_config.get("supports_tools", False) else None
        
        # 创建一个临时 Session 来复用其 _chat_with_api 方法
        temp_session = cls("temp_scheduled_task")
        
        result = await temp_session._chat_with_api(
            messages=messages,
            api_config=api_config,
            tools=tools,
            max_tool_rounds=max_tool_rounds,
            context=context,
        )
        
        return {
            "content": result.content,
            "error": result.error,
            "tool_results": result.tool_results,
            "usage": result.usage,
        }
    
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

        # 日志记录（截断）
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
        
        # 注入上下文参数
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
            images = result.get("images", [])
            error = result.get("error")
            metadata = result.get("metadata", {})
            
            # 简化日志中的图片数据
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
                "_image_urls": images
            }
            
        except Exception as e:
            logger.exception(f"工具执行失败: {e}")
            return {
                "tool_call_id": tool_id,
                "role": "tool",
                "content": json.dumps({"success": False, "error": str(e)}, ensure_ascii=False),
                "_image_urls": []
            }

    async def _chat_with_api(
        self,
        messages: List[Dict[str, Any]],
        api_config: Dict[str, Any],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tool_rounds: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        on_content: Optional[Callable[[str], Any]] = None,
    ) -> ChatResult:
        """
        与 AI API 进行对话，支持工具调用
        """
        if max_tool_rounds is None:
            max_tool_rounds = conf.max_tool_rounds
        
        # 不支持工具调用时，直接单次调用
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
            result = await self._call_ai_api(current_messages, api_config, tools=tools)
            
            # 累加 token 使用量
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
                # 最后一轮，返回最终结果
                return ChatResult(
                    content=content,
                    reasoning_content=result.get("reasoning_content"),
                    tool_results=all_tool_results,
                    usage=total_usage if total_usage["total_tokens"] > 0 else None,
                )
            
            # 工具调用轮次，输出中间内容
            if content and on_content:
                await on_content(content)
            
            # 添加助手消息到当前对话
            assistant_message = result.get("raw_response", {}).get("choices", [{}])[0].get("message", {})
            current_messages.append(assistant_message)
            # 同步到 session 消息历史
            self.messages.append(assistant_message)
            
            # 执行工具调用
            for tool_call in tool_calls:
                tool_result = await self._execute_tool_call(tool_call, context=context)
                all_tool_results.append({
                    "tool_call": tool_call,
                    "result": tool_result
                })
                current_messages.append(tool_result)
                # 同步到 session 消息历史
                self.messages.append(tool_result)
                logger.info(f"工具调用结果: {truncate_log(tool_result['content'])}")
        
        logger.warning(f"达到最大工具调用轮数限制: {max_tool_rounds}")
        return ChatResult(
            content="工具调用次数过多，请简化请求",
            error="达到最大工具调用轮数限制",
            tool_results=all_tool_results,
            usage=total_usage if total_usage["total_tokens"] > 0 else None,
        )


class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self.continuous_users: Dict[str, bool] = {}
        self.choice_mode_users: Dict[str, bool] = {}
        self.choice_guideline_users: Dict[str, Optional[str]] = {}
    
    def get_session_id(self, user_id: int, group_id: Optional[int] = None) -> str:
        if group_id:
            return f"group_{group_id}_user_{user_id}"
        return f"private_{user_id}"
    
    def get_session(self, user_id: int, group_id: Optional[int] = None, persona: Optional[str] = None) -> Session:
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session
            else:
                del self.sessions[session_id]
                if session_id in self.continuous_users:
                    del self.continuous_users[session_id]
        session = Session(session_id, persona)
        if self.continuous_users.get(session_id, False):
            session.continuous_mode = True
        if self.choice_mode_users.get(session_id, False):
            session.choice_mode_enabled = True
            session.choice_guideline = self.choice_guideline_users.get(session_id, None)
        self.sessions[session_id] = session
        return session
    
    def clear_session(self, user_id: int, group_id: Optional[int] = None) -> bool:
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            del self.sessions[session_id]
            if session_id in self.continuous_users:
                del self.continuous_users[session_id]
            if session_id in self.choice_mode_users:
                del self.choice_mode_users[session_id]
            if session_id in self.choice_guideline_users:
                del self.choice_guideline_users[session_id]
            return True
        return False
    
    def set_continuous_mode(self, user_id: int, group_id: Optional[int] = None, enabled: bool = True) -> bool:
        session_id = self.get_session_id(user_id, group_id)
        self.continuous_users[session_id] = enabled
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                session.continuous_mode = enabled
                return True
        return False
    
    def is_continuous_mode(self, user_id: int, group_id: Optional[int] = None) -> bool:
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session.continuous_mode
            else:
                if session_id in self.continuous_users:
                    del self.continuous_users[session_id]
        return self.continuous_users.get(session_id, False)
    
    def set_choice_mode(self, user_id: int, group_id: Optional[int] = None, enabled: bool = True, guideline: Optional[str] = None) -> bool:
        session_id = self.get_session_id(user_id, group_id)
        self.choice_mode_users[session_id] = enabled
        if enabled and guideline:
            self.choice_guideline_users[session_id] = guideline
        elif not enabled:
            if session_id in self.choice_guideline_users:
                del self.choice_guideline_users[session_id]
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                session.choice_mode_enabled = enabled
                session.choice_guideline = guideline if enabled else None
                if not enabled:
                    session.last_choices = {}
                return True
        return False
    
    def get_choice_mode(self, user_id: int, group_id: Optional[int] = None) -> Tuple[bool, Optional[str]]:
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session.choice_mode_enabled, session.choice_guideline
            else:
                if session_id in self.choice_mode_users:
                    del self.choice_mode_users[session_id]
                if session_id in self.choice_guideline_users:
                    del self.choice_guideline_users[session_id]
        enabled = self.choice_mode_users.get(session_id, False)
        guideline = self.choice_guideline_users.get(session_id, None)
        return enabled, guideline
    
    def set_last_choices(self, user_id: int, group_id: Optional[int] = None, choices: Dict[int, str] = None) -> bool:
        session_id = self.get_session_id(user_id, group_id)
        
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                session.last_choices = choices or {}
                return True
        return False
    
    def get_last_choices(self, user_id: int, group_id: Optional[int] = None) -> Dict[int, str]:
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session.last_choices
            else:
                del self.sessions[session_id]
                if session_id in self.continuous_users:
                    del self.continuous_users[session_id]
        return {}
    
    def rollback_messages(self, user_id: int, group_id: Optional[int] = None, count: int = 1) -> int:
        session_id = self.get_session_id(user_id, group_id)
        if session_id not in self.sessions:
            return 0
        session = self.sessions[session_id]
        if not session.messages:
            return 0
        system_msg = None
        start_idx = 0
        if session.messages and session.messages[0].get("role") == "system":
            system_msg = session.messages[0]
            start_idx = 1
        messages_to_delete = count * 2
        other_messages = session.messages[start_idx:]
        
        # 如果消息数不足，只删除存在的
        if len(other_messages) <= messages_to_delete:
            deleted = len(other_messages)
            other_messages = []
        else:
            deleted = messages_to_delete
            other_messages = other_messages[:-messages_to_delete]
        
        # 重新组合
        if system_msg:
            session.messages = [system_msg] + other_messages
        else:
            session.messages = other_messages
        
        session.last_active = time.time()
        return deleted
    
    # ========== SKILL 系统管理方法 ==========
    
    def activate_skill(self, user_id: int, group_id: Optional[int], skill_name: str) -> bool:
        """为用户会话激活 SKILL"""
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session.activate_skill(skill_name)
        return False
    
    def deactivate_skill(self, user_id: int, group_id: Optional[int], skill_name: str) -> bool:
        """为用户会话停用 SKILL"""
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session.deactivate_skill(skill_name)
        return False
    
    def deactivate_all_skills(self, user_id: int, group_id: Optional[int]) -> bool:
        """停用用户会话的所有 SKILL"""
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                session.deactivate_all_skills()
                return True
        return False
    
    def get_active_skills(self, user_id: int, group_id: Optional[int]) -> Set[str]:
        """获取用户会话的已激活 SKILL"""
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session.get_active_skills()
        return set()
    
    def is_skill_active(self, user_id: int, group_id: Optional[int], skill_name: str) -> bool:
        """检查 SKILL 是否已激活"""
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session.is_skill_active(skill_name)
        return False


session_manager = SessionManager()
