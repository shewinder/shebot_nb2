"""Session 管理模块"""
import base64
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union, TYPE_CHECKING

from loguru import logger

from .config import Config
from ._image_store import ImageStore, ImageEntry
from .skills import skill_manager
from .tools import get_tool_function, get_available_tools
from .tools.registry import get_injectable_params
from hoshino.util import aiohttpx, log_json, truncate_log
from hoshino import Message, MessageSegment
from hoshino.sres import Res


from .mcp import mcp_tool_bridge, get_mcp_session_manager
from .md_render import render_text_if_markdown

conf = Config.get_instance('aichat')

# 选项标记的正则表达式
CHOICES_PATTERN = re.compile(r'\[CHOICES\](.*?)\[/CHOICES\]', re.DOTALL)
CHOICE_ITEM_PATTERN = re.compile(r'^(\d+)\.\s*(.+)$', re.MULTILINE)


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
        self.persona = persona
        self.messages: List[Dict[str, Any]] = []
        self.last_active = time.time()
        self.continuous_mode = False
        self._image_store = ImageStore(session_id)
        self._image_store.clear()  # 新建 Session 时清空旧图像缓存
        # SKILL 系统：已激活的 SKILL 名称集合
        self.active_skills: Set[str] = set()
        self._skill_contents: Dict[str, str] = {}
        # 当前正在执行的 SKILL（用于工具权限检查）
        self.active_skill: Optional[str] = None
        # Token 使用量统计
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_tokens: int = 0
        # 从 session_id 解析 user_id 和 group_id
        self.user_id, self.group_id = self._parse_session_id(session_id)
        if persona:
            self.messages.append({"role": "system", "content": persona})
    
    def _append_and_trim(self, message: Dict[str, Any]) -> None:
        """统一的消息追加 + 裁剪入口"""
        self.messages.append(message)
        
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

    def add_message(self, role: str, content: Union[str, List[Dict[str, Any]]]):
        """添加标准 user/assistant 消息"""
        self._append_and_trim({"role": role, "content": content})

    def add_raw_message(self, message: Dict[str, Any]) -> None:
        """添加完整 API 格式消息（支持 tool_calls、tool 等）"""
        self._append_and_trim(message)
    
    async def store_user_image(self, image_data: str) -> str:
        entry = await self._image_store.store(image_data, "user")
        self.last_active = time.time()
        return entry.identifier
    
    async def store_ai_image(self, image_data: str) -> str:
        entry = await self._image_store.store(image_data, "ai")
        self.last_active = time.time()
        return entry.identifier
    
    def resolve_image_identifier(self, identifier: str) -> Optional[str]:
        return self._image_store.get_data_url(identifier)
    
    async def get_image_segment(self, identifier: str) -> Optional["MessageSegment"]:
        """根据标识符获取图片 MessageSegment"""
        entry = self._image_store.get(identifier)
        if not entry or not entry.file_path.exists():
            return None
        try:
            return Res.image(entry.file_path)
        except Exception:
            return None
    
    def list_images(self) -> List[ImageEntry]:
        """列出当前会话所有图像（供 Skill 脚本使用）"""
        return self._image_store.list_all()
    
    async def build_message(
        self,
        content: str,
        enable_markdown: bool = False,
        markdown_min_length: int = 100
    ) -> "List[Message]":
        """构建消息对象列表
        
        根据是否启用 Markdown，采用不同的处理策略：
        
        **未启用 Markdown**：图文混合，标识符替换为图片
        - 返回单个 Message，包含文本和图片段
        
        **启用 Markdown**：分离处理
        - 文本部分走 Markdown 渲染（返回渲染后的图片或原文本）
        - 标识符图片单独提取，各自作为独立 Message
        - 返回 Message 列表
        
        Args:
            content: 原始内容，可能包含图片标识符
            enable_markdown: 是否启用 Markdown 渲染
            markdown_min_length: Markdown 渲染的最小文本长度
        
        Returns:
            Message 列表（未启用 Markdown 时长度为1，启用时可能多个）
        """
        IMAGE_PATTERN = re.compile(r'<(user_image_\d+|ai_image_\d+)>')
        identifiers = IMAGE_PATTERN.findall(content)
        clean_text = IMAGE_PATTERN.sub('', content).strip()
        
        # 获取所有图片段
        image_segments = []
        for identifier in identifiers:
            img_seg = await self.get_image_segment(identifier)
            if img_seg:
                image_segments.append(img_seg)
        
        if not enable_markdown:
            # 图片数量较多时(>3张)分批发送，避免QQ协议超时
            if len(image_segments) > 3:
                messages = []
                if clean_text:
                    messages.append(Message(MessageSegment.text(clean_text)))
                for img_seg in image_segments:
                    messages.append(Message(img_seg))
                return messages
            else:
                msg = Message()
                if clean_text:
                    msg = MessageSegment.text(clean_text)
                for img_seg in image_segments:
                    msg = msg + img_seg if msg else img_seg
                return [msg] if msg else []
        
        # 模式2：启用 Markdown，分离处理
        messages = []
        
        # 处理文本（Markdown 渲染）
        if clean_text:
            text_msg = None
            if len(clean_text) >= markdown_min_length:
                try:
                    img_bytes = await render_text_if_markdown(clean_text, min_length=markdown_min_length)
                    if img_bytes:
                        text_msg = MessageSegment.image(file=img_bytes)
                except Exception:
                    pass
            
            if not text_msg:
                text_msg = MessageSegment.text(clean_text)
            
            messages.append(Message(text_msg))
        
        # 每个图片作为独立 Message
        for img_seg in image_segments:
            messages.append(Message(img_seg))
        
        return messages
    
    @staticmethod
    def build_image_rules_prompt() -> str:
        """构建图片发送规则提示（固定内容，用于系统消息）"""
        return """
【图片发送规则】
当需要向用户展示图片时，请遵循以下规则：
1. 在回复文本中直接写出图片标识符（如 <user_image_1> 或 <ai_image_1>）
2. 系统会自动检测标识符、发送对应图片，并将标识符从用户看到的文本中移除
3. 正确示例：
   你回复："这是<user_image_1>，一只可爱的猫"
   用户看到：[图片] + "这是一只可爱的猫"
4. 错误示例（不要这样做）：
   "这是你发的图片"（没有标识符，用户看不到图片）
   "图片在这：<user_image_1>"（标识符会被移除，露出空白）
5. generate_image/edit_image 工具的 image_identifiers 参数仍可使用这些标识符
【规则结束】
"""
    
    @staticmethod
    def build_execution_style_prompt() -> str:
        """构建执行风格提示（固定内容，用于系统消息）"""
        return """
【执行风格指南】
调用工具执行任务时，遵循以下风格：

✅ 允许做的事情（简洁即可）：
- 开始执行前简单确认（如"好的"、"稍等"）
- 操作失败后说明原因并重试
- 最终输出完整结果

❌ 禁止做的事情（废话/冗余）：
- "首先让我..."、"第一步..."、"接下来..."等步骤预告
- 详细解释每一步在做什么（如"正在获取日期..."、"正在调用API..."）
- 分多条消息输出中间过程
- 询问用户"需要我帮你做吗？"（用户已经提出了请求）

🎯 原则：
1. 能直接完成的，直接给出结果
2. 需要用户等待的，简单回复"好的"或"稍等"即可，不要啰嗦
3. 一次工具调用失败要重试时，可以简单说明失败原因
4. 最终结果要完整，但不要冗余

正确示例：
用户：查询北京天气
AI：[直接调用 get_weather 工具]
AI回复：🌤️ 北京今天晴，15-22℃

用户：生成一张猫的图片
AI：[调用 generate_image]
AI回复：🎨 已生成：<ai_image_1>

错误示例（过于啰嗦）：
❌ "我来帮你查询北京天气，首先需要获取当前城市信息..."
❌ "正在调用天气API接口获取数据..."
❌ "根据查询结果分析，北京今天的天气情况是..."
【风格指南结束】
"""
    
    def build_image_list_prompt(self) -> str:
        """构建可用图片列表提示（动态内容，附加到用户消息）"""
        images = self._image_store.list_all()
        if not images:
            return ""
        
        lines = [
            "",
            "=" * 40,
            "【当前可用图片】",
        ]
        
        for img in images:
            meta = f"{img.width}x{img.height}" if img.width and img.height else "未知尺寸"
            lines.append(f"{img.identifier} ({img.source}, {img.format}, {meta})")
        
        lines.extend([
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
    
    def get_last_choices(self) -> Dict[int, str]:
        """动态从消息历史中解析选项（以最后一条 user 消息为界，避免找回旧选项）"""
        last_user_idx = -1
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].get("role") == "user":
                last_user_idx = i
                break
        if last_user_idx >= 0:
            for msg in reversed(self.messages[last_user_idx:]):
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        _, choices = parse_choices_from_response(content)
                        if choices:
                            return choices
        return {}
    
    # ========== SKILL 系统方法 ==========
    
    def activate_skill(self, skill_name: str) -> Tuple[bool, str, Optional[str]]:
        """激活一个 SKILL
        
        Returns:
            (success, message, content)
        """
        skill = skill_manager.get_skill(skill_name)
        if not skill:
            return False, f"SKILL '{skill_name}' 不存在", None
        
        if skill_name in self.active_skills:
            return True, f"SKILL '{skill_name}' 已经激活", skill.content
        
        # 限制单个会话最多激活 SKILL
        if len(self.active_skills) >= conf.skill_max_per_session:
            return False, f"激活 '{skill_name}' 会导致循环依赖，已阻止", None
        
        self.active_skills.add(skill_name)
        self._skill_contents[skill_name] = skill.content
        self.last_active = time.time()
        logger.info(f"Session {self.session_id} 激活 SKILL: {skill_name}")
        return True, f"SKILL '{skill_name}' 已激活", skill.content
    
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
    
    @staticmethod
    def _parse_session_id(session_id: str) -> Tuple[Optional[int], Optional[int]]:
        """从 session_id 解析 user_id 和 group_id
        
        格式：
        - group_{group_id}_user_{user_id} -> (user_id, group_id)
        - private_{user_id} -> (user_id, None)
        
        Returns:
            Tuple[user_id, group_id]
        """
        user_id = None
        group_id = None
        
        try:
            if session_id.startswith("group_"):
                # group_{group_id}_user_{user_id}
                parts = session_id.split("_")
                if len(parts) >= 4:
                    group_id = int(parts[1])
                    user_id = int(parts[3])
            elif session_id.startswith("private_"):
                # private_{user_id}
                user_id = int(session_id.split("_")[1])
        except (ValueError, IndexError):
            pass
        
        return user_id, group_id
    
    def _build_env_info(self, event: Optional[Any] = None) -> str:
        """构建环境信息（XML格式）
        
        Args:
            event: 消息事件（优先使用），如为 None 则使用 session 解析的值
        """
        from datetime import datetime
        
        attrs = []
        
        # 优先从 event 获取，否则使用 session 解析的值
        if event:
            user_id = event.user_id
            group_id = getattr(event, 'group_id', None)
        else:
            user_id = self.user_id
            group_id = self.group_id
        
        if user_id:
            attrs.append(f'user_id="{user_id}"')
        if group_id:
            attrs.append(f'group_id="{group_id}"')
        
        # 当前日期（避免AI使用错误日期，只注入日期不影响缓存）
        current_date = datetime.now().strftime("%Y-%m-%d")
        attrs.append(f'current_date="{current_date}"')
        
        return f'<context type="environment" {" ".join(attrs)} />'
    
    async def _build_messages_for_chat(self, event: Optional[Any] = None) -> None:
        """构建用于 API 调用的消息列表，直接更新 self.messages
        
        使用内部保存的 persona 以及 event 构建环境信息
        
        Args:
            event: 消息事件（可选，用于构建环境信息）
        """
        messages: List[Dict[str, Any]] = []
        image_list_prompt = self.build_image_list_prompt()
        
        # 构建系统消息内容（使用内部保存的 persona）
        system_content = self.persona or ""
        
        # 环境信息（从 event 构建，包含当前日期时间）
        env_info = self._build_env_info(event)
        if env_info:
            system_content = f"{system_content}\n\n{env_info}" if system_content else env_info
        
        # 工具提示
        tool_hint = "<instructions>\n你可以调用 get_current_time 工具获取当前准确时间。\n</instructions>"
        system_content = f"{system_content}\n\n{tool_hint}" if system_content else tool_hint
        
        # 执行风格指南（固定内容，提高缓存利用率）
        execution_style = self.build_execution_style_prompt()
        system_content = f"{system_content}\n\n{execution_style}"
        
        # 图片发送规则（固定内容，提高缓存利用率）
        image_rules = self.build_image_rules_prompt()
        system_content = f"{system_content}\n\n{image_rules}"
        
        # SKILL 内容注入
        if conf.enable_skills:
            skill_summary = skill_manager.get_metadata_summary()
            if skill_summary:
                system_content = f"{system_content}\n\n{skill_summary}" if system_content else skill_summary
                logger.debug(f"[SKILL] 可用 SKILL 列表已注入")
            
            # 获取已激活的 SKILL
            active_skills = self.active_skills
            logger.info(f"[SKILL] 当前会话已激活 SKILL: {active_skills if active_skills else '无'}")
            
            skill_content = skill_manager.get_injected_content(self.active_skills)
            if skill_content:
                content_preview = skill_content[:500] + "..." if len(skill_content) > 500 else skill_content
                logger.info(f"[SKILL] 注入内容预览:\n{content_preview}")
                system_content = f"{system_content}\n\n{skill_content}" if system_content else skill_content
            else:
                logger.info(f"[SKILL] 没有需要注入的 SKILL 内容")
        
        # MCP 内容注入
        if conf.enable_mcp:
            # 1. 注入 MCP server 摘要（用于 AI 选择）
            mcp_summary = mcp_tool_bridge.get_metadata_summary()
            if mcp_summary:
                system_content = f"{system_content}\n\n{mcp_summary}" if system_content else mcp_summary
                logger.debug("[MCP] MCP server 摘要已注入")
            
            # 2. 记录已激活的 MCP server
            mcp_sm = get_mcp_session_manager()
            active_mcp_servers = mcp_sm.get_active_servers(self.session_id) if mcp_sm else []
            logger.info(f"[MCP] 当前会话已激活 MCP server: {active_mcp_servers if active_mcp_servers else '无'}")
        
        # 组装消息列表
        non_system_msgs = [msg for msg in self.messages if msg.get("role") != "system"]
        
        if system_content:
            messages.append({"role": "system", "content": system_content})
            # 同步更新 session.messages，供 web 端调试查看
            self.messages = [{"role": "system", "content": system_content}] + non_system_msgs
            # 调试日志：记录完整系统消息（截断）
            system_log = system_content[:2000] + "...[截断]" if len(system_content) > 2000 else system_content
            logger.debug(f"[SKILL] 完整系统消息:\n{system_log}")
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
        bot: Optional[Any] = None,
        event: Optional[Any] = None,
        on_content: Optional[Callable[[str], Any]] = None,
    ) -> ChatResult:
        """
        执行对话调用，完全内聚，自动处理消息构建和工具获取
        
        Args:
            api_config: API 配置
            bot: Bot 实例（用于工具注入）
            event: 消息事件（用于构建环境信息和工具注入）
            on_content: 内容回调（用于流式输出）
        
        Returns:
            ChatResult: 对话结果
        """
        # 1. 内部自动构建消息
        await self._build_messages_for_chat(event)
        
        # 2. 内部自动获取 tools（传入 session 以支持 MCP 渐进式加载）
        tools = None
        if api_config.get("supports_tools", False):
            tools = await get_available_tools(session=self)
        
        # 3. 构建上下文（注入 session、bot、event）
        chat_context: Dict[str, Any] = {'session': self}
        if bot:
            chat_context['bot'] = bot
        if event:
            chat_context['event'] = event
        
        # 4. 调用 API
        result = await self._chat_with_api(
            messages=self.messages,
            api_config=api_config,
            tools=tools,
            context=chat_context,
            on_content=on_content,
        )
        
        # 5. 自动累加 token 使用量
        if result.usage:
            prompt_tokens = result.usage.get("prompt_tokens", 0) or 0
            completion_tokens = result.usage.get("completion_tokens", 0) or 0
            if prompt_tokens > 0 or completion_tokens > 0:
                self.add_tokens(prompt_tokens, completion_tokens)
        
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
        
        # 解析参数
        try:
            arguments = json.loads(arguments_str)
        except json.JSONDecodeError:
            logger.error(f"工具参数解析失败: {arguments_str}")
            return {
                "tool_call_id": tool_id,
                "role": "tool",
                "content": json.dumps({"success": False, "error": "参数解析失败"}, ensure_ascii=False),
            }
        
        # 获取工具函数
        tool_func = get_tool_function(function_name)
        if not tool_func:
            logger.error(f"未找到工具: {function_name}")
            return {
                "tool_call_id": tool_id,
                "role": "tool",
                "content": json.dumps({"success": False, "error": f"未知工具: {function_name}"}, ensure_ascii=False),
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
            error = result.get("error")
            metadata = result.get("metadata", {})
            
            # 简化日志中的图片数据（如果 content 中包含 base64）
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
            
            # 每轮重新获取工具列表，支持 MCP 渐进式加载（激活后可立即使用）
            if round_num > 0 and api_config.get("supports_tools", False):
                tools = await get_available_tools(session=self)
                logger.debug(f"[MCP] 第 {round_num + 1} 轮重新获取工具，共 {len(tools) if tools else 0} 个")
            
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
            self.add_raw_message(assistant_message)
            
            # 执行工具调用
            for tool_call in tool_calls:
                tool_result = await self._execute_tool_call(tool_call, context=context)
                all_tool_results.append({
                    "tool_call": tool_call,
                    "result": tool_result
                })
                current_messages.append(tool_result)
                # 同步到 session 消息历史
                self.add_raw_message(tool_result)
                # 打印完整 stdout/stderr 以便调试脚本问题
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


class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
    
    def get_session_id(self, user_id: int, group_id: Optional[int] = None) -> str:
        if group_id:
            return f"group_{group_id}_user_{user_id}"
        return f"private_{user_id}"
    
    def _remove_session(self, session_id: str) -> None:
        """统一删除 session 入口，同时清理 MCP 状态"""
        if session_id in self.sessions:
            del self.sessions[session_id]
        
        mcp_sm = get_mcp_session_manager()
        if mcp_sm is not None:
            try:
                mcp_sm.clear_session(session_id)
            except Exception:
                pass
    
    def get_session(self, user_id: int, group_id: Optional[int] = None) -> Optional[Session]:
        """获取已存在且未过期的 session，不存在或过期返回 None"""
        session_id = self.get_session_id(user_id, group_id)
        session = self.sessions.get(session_id)
        if not session:
            return None
        if session.is_expired():
            self._remove_session(session_id)
            return None
        return session
    
    def create_session(self, user_id: int, group_id: Optional[int] = None,
                       persona: Optional[str] = None) -> Session:
        """显式创建新 session，如存在旧 session 先清理"""
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            self._remove_session(session_id)
        session = Session(session_id, persona)
        self.sessions[session_id] = session
        return session
    
    def get_or_create_session(self, user_id: int, group_id: Optional[int] = None,
                              persona: Optional[str] = None) -> Session:
        """获取已存在的 session，不存在则创建"""
        session = self.get_session(user_id, group_id)
        if not session:
            session = self.create_session(user_id, group_id, persona)
        return session
    
    def has_session(self, user_id: int, group_id: Optional[int] = None) -> bool:
        """检查是否存在未过期的活跃 session"""
        return self.get_session(user_id, group_id) is not None
    
    def clear_session(self, user_id: int, group_id: Optional[int] = None) -> bool:
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            self._remove_session(session_id)
            return True
        return False


session_manager = SessionManager()
