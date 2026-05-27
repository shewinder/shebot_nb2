"""Session 管理模块"""
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from loguru import logger

from .config import Config
from ._image_store import ImageStore, ImageEntry
from .memory import memory_store
from .skills import skill_manager

from .mcp import mcp_tool_bridge, get_mcp_session_manager

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


class Session:
    def __init__(self, session_id: str, user_id: int,
                 persona: Optional[str] = None, group_id: Optional[int] = None,
                 register: bool = False):
        self.session_id = session_id
        self.persona = persona
        self.messages: List[Dict[str, Any]] = []
        self.last_active = time.time()
        self.continuous_mode = False
        self._image_store = ImageStore(session_id)
        self._image_store.clear()  # 新建 Session 时清空旧图像缓存
        # SKILL 系统：已激活的 SKILL 名称集合
        self.active_skills: Set[str] = set()
        # 当前正在执行的 SKILL（用于工具权限检查）
        self.active_skill: Optional[str] = None
        # Token 使用量统计
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_tokens: int = 0
        self.user_id = user_id
        self.group_id = group_id
        self.agent_label: str = "main"  # 日志标识：main / sub:vision / sub:search

        if register:
            session_manager.sessions[self.session_id] = self

    @property
    def _tag(self) -> str:
        return f"[Agent:{self.agent_label}]"

    def _append_message(self, message: Dict[str, Any]) -> None:
        """追加消息到历史"""
        self.messages.append(message)
        self.last_active = time.time()

    def add_message(self, role: str, content: Union[str, List[Dict[str, Any]]]):
        """添加标准 user/assistant 消息"""
        self._append_message({"role": role, "content": content})

    def add_raw_message(self, message: Dict[str, Any]) -> None:
        """添加完整 API 格式消息（支持 tool_calls、tool 等）"""
        self._append_message(message)
    
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
    
    def list_images(self) -> List[ImageEntry]:
        """列出当前会话所有图像（供 Skill 脚本使用）"""
        return self._image_store.list_all()

    @staticmethod
    def build_image_rules_prompt() -> str:
        """构建多媒体发送规则提示（固定内容，用于系统消息）"""
        return """
【多媒体发送规则】
当需要向用户展示图片、@用户或戳一戳时，请遵循以下规则：

📷 图片标识符：
1. 在回复文本中直接写出图片标识符（如 <user_image_1> 或 <ai_image_1>）
2. 系统会自动检测标识符、发送对应图片，并将标识符从用户看到的文本中移除
3. 正确示例：
   你回复："这是<user_image_1>，一只可爱的猫"
   用户看到：[图片] + "这是一只可爱的猫"
4. 不要在同一条回复中重复引用同一个图片标识符
5. generate_image/edit_image 工具的 image_identifiers 参数仍可使用这些标识符

👤 @用户：
1. 需要提及/点名某人时，使用 <@QQ号> 格式
2. 正确示例：
   你回复："<@12345>早上好" → 用户看到：@某人 早上好
   你回复："<@12345> <@67890> 请确认" → @两人
3. 注意：不要虚构 QQ 号，使用 context 中的 user_id

【规则结束】
"""
    
    @staticmethod
    def build_mode_prelude() -> str:
        """构建系统模式说明和执行规则（放在最前面）"""
        return """【系统模式与规则】

🔧 工具执行 — 调用工具完成任务时：
  · 简洁直接，能一步做完的不分步
  · 可简单确认（"好的""稍等"），可保留角色口吻，但去掉行动叙事（"让我来帮你..."）
  · 不要问"需要我帮你做吗"、不要步骤预告、不要解释正在做什么
  ✔️ "好的" → 调工具 → 返回结果
  ❌ "好的，让我来帮你查一下，这就去调用天气API..."
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
        self.last_active = time.time()
        logger.info(f"{self._tag} Session 激活 SKILL: {skill_name}")
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
    


    def _build_env_info(self, event: Optional[Any] = None) -> str:
        """构建环境信息（XML格式）
        
        Args:
            event: 消息事件（优先使用），如为 None 则使用 session 解析的值
        """
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
    
    async def _build_messages_for_chat(self, event: Optional[Any] = None) -> List[Dict[str, Any]]:
        """构建用于 API 调用的消息列表

        System prompt 只保留静态核心指令（缓存友好）。
        动态内容（skill、mcp、memory、env）作为上下文消息对注入。

        Args:
            event: 消息事件（可选，用于构建环境信息）

        Returns:
            完整 API 消息列表
        """
        # 1. 构建 system content
        # 顺序：模式说明（顶）→ 功能规则（优先级高）→ 角色设定 → 环境/工具（尾）
        parts: List[str] = []

        # 系统模式说明 + 执行规则（合并，先于角色设定以提升权重）
        parts.append(self.build_mode_prelude())

        # 图片发送规则（功能规则）
        parts.append(self.build_image_rules_prompt())

        # 角色设定（persona 放后面，不影响工具执行规则的优先级）
        if self.persona:
            parts.append(f"【角色设定】\n{self.persona}")

        # 环境信息
        env_info = self._build_env_info(event)
        if env_info:
            parts.append(env_info)

        # 工具提示
        parts.append("<instructions>\n你可以调用 get_current_time 工具获取当前准确时间。\n</instructions>")

        system_content = "\n\n".join(parts)

        system_msg = {"role": "system", "content": system_content}

        # 2. 构建动态上下文
        context_parts: List[str] = []

        # SKILL 内容注入
        if conf.enable_skills:
            skill_summary = skill_manager.get_metadata_summary()
            if skill_summary:
                context_parts.append(skill_summary)
                logger.debug(f"{self._tag} [SKILL] 可用 SKILL 列表已注入")

            active_skills = self.active_skills
            logger.info(f"{self._tag} [SKILL] 当前会话已激活 SKILL: {active_skills if active_skills else '无'}")

            skill_content = skill_manager.get_injected_content(self.active_skills)
            if skill_content:
                content_preview = skill_content[:500] + "..." if len(skill_content) > 500 else skill_content
                logger.info(f"{self._tag} [SKILL] 注入内容预览:\n{content_preview}")
                context_parts.append(skill_content)
            else:
                logger.info(f"{self._tag} [SKILL] 没有需要注入的 SKILL 内容")

        # MCP 内容注入
        if conf.enable_mcp:
            mcp_summary = mcp_tool_bridge.get_metadata_summary()
            if mcp_summary:
                context_parts.append(mcp_summary)
                logger.debug(f"{self._tag} [MCP] MCP server 摘要已注入")

            mcp_sm = get_mcp_session_manager()
            active_mcp_servers = mcp_sm.get_active_servers(self.session_id) if mcp_sm else []
            logger.info(f"{self._tag} [MCP] 当前会话已激活 MCP server: {active_mcp_servers if active_mcp_servers else '无'}")

        # 子 Agent 类型注入（仅主 Agent 可见，子 Agent 不需要知道）
        if self.agent_label == "main":
            from ._agent_runner import SUBAGENT_TYPES
            if SUBAGENT_TYPES:
                lines = ["【可用的子 Agent 类型】", "使用 delegate_task 工具时，通过 type 参数选择类型："]
                for t in SUBAGENT_TYPES.values():
                    lines.append(f"  · {t.name}: {t.description}")
                context_parts.append("\n".join(lines))

        # 记忆注入
        if conf.enable_memory and self.user_id:
            try:
                memory_text = await memory_store.get_inject_text(self.user_id, conf.memory_max_inject_length)
                if memory_text:
                    context_parts.append(f"【关于该用户的历史记忆】\n{memory_text}")
                    logger.debug(f"{self._tag} [Memory] 已注入记忆，长度: {len(memory_text)}")
            except Exception as e:
                logger.warning(f"[Memory] 注入记忆失败: {e}")

        context_msgs: List[Dict[str, Any]] = []
        if context_parts:
            context_text = "\n\n".join(p for p in context_parts if p)
            context_msgs = [
                {"role": "user", "content": context_text},
                {"role": "assistant", "content": "已了解当前系统上下文。"},
            ]

        # 3. 图片列表提示附加到历史最后一条 user 消息
        image_list_prompt = self.build_image_list_prompt()
        if image_list_prompt:
            for msg in reversed(self.messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    # 避免重复附加
                    if isinstance(content, str) and image_list_prompt in content:
                        break
                    if isinstance(content, list):
                        texts = [item.get("text", "") for item in content if isinstance(item, dict)]
                        if any(image_list_prompt in t for t in texts):
                            break
                    if isinstance(content, list):
                        content.append({"type": "text", "text": image_list_prompt})
                    elif isinstance(content, str):
                        msg["content"] = content + image_list_prompt
                    break

        # 调试日志
        system_log = system_content[:2000] + "...[截断]" if len(system_content) > 2000 else system_content
        logger.debug(f"[SKILL] 完整系统消息:\n{system_log}")

        # 4. 返回完整 API 消息（system + context + history）
        return [system_msg] + context_msgs + self.messages
    


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
            logger.debug(f"[_remove_session] session={session_id} 已从内存中删除")
        
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
        session = Session(session_id, user_id, persona=persona, group_id=group_id)
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
