"""Session 管理模块"""
import asyncio
import copy
import json
import re
import shutil
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from loguru import logger

from .config import Config
from ._image_store import ImageStore, ImageEntry
from ._image_store_core import ImageStoreCore
from ._video_store_core import VideoStoreCore
from .memory import memory_store
from .skills import skill_manager
from .subagent_types import SUBAGENT_TYPES

from .mcp import mcp_tool_bridge, get_mcp_session_manager

conf = Config.get_instance('aichat')

# per-session 异步锁注册表：串行化同一会话的并发消息处理，
# 防止历史消息交错、回滚错位（chat.py 在消息编排前获取 session.lock）。
_session_locks: Dict[str, asyncio.Lock] = {}


@dataclass
class PendingInput:
    """运行中会话暂存的用户消息快照，不持有可变消息对象。"""

    user_input: str
    image_urls: List[str]
    video_urls: List[str]
    bot: Any
    event: Any
    raw_message: str = ""
    sequence: int = 0


def _get_session_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _session_locks:
        _session_locks[session_id] = asyncio.Lock()
    return _session_locks[session_id]


def _copy_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """拷贝消息字典；list 型 content（多模态）拷贝外层列表，避免追加时污染持久历史"""
    copied = dict(message)
    content = copied.get("content")
    if isinstance(content, list):
        copied["content"] = list(content)
    return copied

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
    MAX_PENDING_INPUTS = 32
    SNAPSHOT_VERSION = 1
    MAX_PERSISTED_MESSAGES = 400
    MAX_PERSISTED_STRING_LENGTH = 20000
    INLINE_MEDIA_PATTERN = re.compile(
        r"data:(?:image|video)/[^;\s]+;base64,[A-Za-z0-9+/=]+"
    )

    def __init__(self, session_id: str, user_id: int,
                 persona: Optional[str] = None, group_id: Optional[int] = None,
                 register: bool = False, persistent: bool = False,
                 load_existing: bool = False):
        if not session_id or Path(session_id).name != session_id or session_id in {".", ".."}:
            raise ValueError(f"非法 session_id: {session_id!r}")
        self.session_id = session_id
        self.persistent = persistent
        self.persona = persona
        self.messages: List[Dict[str, Any]] = []
        self.last_active = time.time()
        self.continuous_mode = False
        self._session_dir = ImageStoreCore._resolve_session_dir(session_id)
        if not self.persistent:
            self._clear_session_dir()
        self._image_store = ImageStore(session_id)
        # 视频存储（独立标识符 <ai_video_N> / <user_video_N>，与图片同属 session 目录）
        self._video_store = VideoStoreCore(session_id)
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
        # Reply 管道状态：最近一条 user 消息时间（用于图片兜底补发）与
        # 本轮已发送的图片标识符（会话级去重）
        self.last_user_msg_at: float = time.time()
        self._turn_sent_images: Set[str] = set()
        self._turn_state_lock = threading.Lock()
        self._turn_active = False
        self._turn_id: Optional[str] = None
        self._pending_inputs: deque[PendingInput] = deque()
        self._pending_sequence = 0
        self._persistence_lock = threading.Lock()

        if self.persistent and load_existing:
            self._load_snapshot()

        if register:
            session_manager.sessions[self.session_id] = self

    @property
    def lock(self) -> asyncio.Lock:
        """本会话的互斥锁，消息编排（构建上下文→追加历史→执行）须持锁进行"""
        return _get_session_lock(self.session_id)

    @property
    def _tag(self) -> str:
        return f"[Agent:{self.agent_label}]"

    def _append_message(self, message: Dict[str, Any]) -> None:
        """追加消息到历史"""
        self.messages.append(message)
        self.last_active = time.time()
        self.save_snapshot()

    def add_message(self, role: str, content: Union[str, List[Dict[str, Any]]]):
        """添加标准 user/assistant 消息"""
        if role == "user":
            # 新一轮对话开始：重置发送去重状态
            self.last_user_msg_at = time.time()
            self._turn_sent_images.clear()
        self._append_message({"role": role, "content": content})

    def add_raw_message(self, message: Dict[str, Any]) -> None:
        """添加完整 API 格式消息（支持 tool_calls、tool 等）"""
        self._append_message(message)

    def set_continuous_mode(self, enabled: bool) -> None:
        """设置连续对话模式并保存会话状态"""
        self.continuous_mode = bool(enabled)
        self.last_active = time.time()
        self.save_snapshot()

    def try_begin_turn(self) -> bool:
        """兼容旧调用方，原子登记当前会话的执行者。"""
        with self._turn_state_lock:
            if self._turn_active:
                return False
            self._turn_active = True
            self._turn_id = uuid.uuid4().hex[:12]
            self.last_active = time.time()
            self.save_snapshot()
            return True

    def claim_turn_or_enqueue(
        self,
        user_input: str,
        image_urls: List[str],
        video_urls: List[str],
        bot: Any,
        event: Any,
        raw_message: str = "",
    ) -> Tuple[bool, Optional[int], Optional[str], List[PendingInput]]:
        """原子地成为执行者或加入当前回合，消除入口检查竞态。"""
        with self._turn_state_lock:
            if not self._turn_active:
                preceding = list(self._pending_inputs)
                self._pending_inputs.clear()
                self._turn_active = True
                self._turn_id = uuid.uuid4().hex[:12]
                self.last_active = time.time()
                self.save_snapshot()
                return True, None, self._turn_id, preceding
            if len(self._pending_inputs) >= self.MAX_PENDING_INPUTS:
                return False, None, self._turn_id, []
            self._pending_sequence += 1
            self._pending_inputs.append(PendingInput(
                user_input=str(user_input),
                image_urls=list(image_urls),
                video_urls=list(video_urls),
                bot=bot,
                event=event,
                raw_message=str(raw_message),
                sequence=self._pending_sequence,
            ))
            self.last_active = time.time()
            self.save_snapshot()
            return False, self._pending_sequence, self._turn_id, []

    @property
    def turn_active(self) -> bool:
        """当前是否已有前台对话回合在执行。"""
        with self._turn_state_lock:
            return self._turn_active

    @property
    def turn_id(self) -> Optional[str]:
        """当前前台对话回合 ID，用于日志和诊断。"""
        with self._turn_state_lock:
            return self._turn_id

    def enqueue_pending_input(
        self,
        user_input: str,
        image_urls: List[str],
        video_urls: List[str],
        bot: Any,
        event: Any,
        raw_message: str = "",
    ) -> Optional[int]:
        """运行中暂存一条消息，返回队列序号；非活跃或队列满返回 None。"""
        with self._turn_state_lock:
            if not self._turn_active or len(self._pending_inputs) >= self.MAX_PENDING_INPUTS:
                return None
            self._pending_sequence += 1
            self._pending_inputs.append(PendingInput(
                user_input=str(user_input),
                image_urls=list(image_urls),
                video_urls=list(video_urls),
                bot=bot,
                event=event,
                raw_message=str(raw_message),
                sequence=self._pending_sequence,
            ))
            self.last_active = time.time()
            self.save_snapshot()
            return self._pending_sequence

    def drain_pending_inputs(self) -> List[PendingInput]:
        """按 FIFO 取出当前待插入消息。"""
        with self._turn_state_lock:
            items = list(self._pending_inputs)
            self._pending_inputs.clear()
            if items:
                self.last_active = time.time()
                self.save_snapshot()
            return items

    def finish_turn_or_drain_pending_inputs(self) -> Optional[List[PendingInput]]:
        """原子地取出 pending；队列为空时释放执行权。"""
        with self._turn_state_lock:
            if self._pending_inputs:
                items = list(self._pending_inputs)
                self._pending_inputs.clear()
                self.last_active = time.time()
                self.save_snapshot()
                return items
            self._turn_active = False
            self._turn_id = None
            self.save_snapshot()
            return None

    def requeue_pending_inputs(self, items: List[PendingInput]) -> None:
        """处理失败时将消息按原顺序放回队首，避免媒体准备异常导致丢消息。"""
        if not items:
            return
        with self._turn_state_lock:
            for item in reversed(items):
                self._pending_inputs.appendleft(item)
            self.last_active = time.time()
            self.save_snapshot()

    def pending_input_count(self) -> int:
        """返回当前待处理消息数量。"""
        with self._turn_state_lock:
            return len(self._pending_inputs)

    def end_turn(self, expected_turn_id: Optional[str] = None) -> None:
        """释放当前回合执行权，可避免旧执行者覆盖新执行者状态。"""
        with self._turn_state_lock:
            if expected_turn_id is not None and self._turn_id != expected_turn_id:
                return
            self._turn_active = False
            self._turn_id = None

    def clear_pending_inputs(self) -> int:
        """清空尚未进入上下文的消息，返回清理数量。"""
        with self._turn_state_lock:
            count = len(self._pending_inputs)
            self._pending_inputs.clear()
            self.save_snapshot()
            return count
    
    async def store_user_image(self, image_data: str, url: Optional[str] = None) -> str:
        entry = await self._image_store.store(image_data, "user", url=url)
        self.last_active = time.time()
        self.save_snapshot()
        return entry.identifier

    async def store_ai_image(self, image_data: str, url: Optional[str] = None) -> str:
        entry = await self._image_store.store(image_data, "ai", url=url)
        self.last_active = time.time()
        self.save_snapshot()
        return entry.identifier
    
    def resolve_image_identifier(self, identifier: str) -> Optional[str]:
        return self._image_store.get_data_url(identifier)
    
    def list_images(self) -> List[ImageEntry]:
        """列出当前会话所有图像（供 Skill 脚本使用）"""
        return self._image_store.list_all()

    async def store_ai_video_bytes(self, data: bytes) -> str:
        """存储 AI 生成的视频字节，返回标识符（如 <ai_video_1>）

        async 与 store_ai_image 对齐（曾为同步方法导致调用方 await 崩溃）
        """
        entry = self._video_store.store_bytes(data, "ai", "mp4")
        self.last_active = time.time()
        self.save_snapshot()
        return entry.identifier

    async def store_user_video(self, data: bytes, url: Optional[str] = None) -> str:
        """存储用户上传的视频字节，返回标识符（如 <user_video_1>）

        async 与 store_user_image 对齐
        """
        entry = self._video_store.store_bytes(data, "user", "mp4", url=url)
        self.last_active = time.time()
        self.save_snapshot()
        return entry.identifier

    def resolve_video_file(self, identifier: str) -> Optional[Path]:
        """根据视频标识符解析本地文件路径"""
        return self._video_store.get_file_path(identifier)

    def list_videos(self) -> List[Any]:
        """列出当前会话所有视频"""
        return self._video_store.list_all()

    @staticmethod
    def build_image_rules_prompt() -> str:
        """构建多媒体发送规则提示（固定内容，用于系统消息）"""
        return """
【多媒体发送规则】
图片和视频标识符是会话内部的资源句柄，不是普通引用文本。

📷 图片/视频标识符：
1. 只有在用户明确要求发送、展示或重新发送某个媒体，或当前任务已经生成/处理出需要交付的最终媒体成品时，才在最终回复中输出对应标识符
2. 分析、描述、比较、确认收到图片或视频时，直接用“这张图片”“这个视频”等文字回答，不要输出任何媒体标识符
3. 不要为了证明已经看过图片或视频而引用或重新发送它；不要把工具返回的标识符复制到普通说明文字中
4. 调用工具或子 Agent 时，可以按工具参数要求传入媒体标识符；这不代表需要在最终回复中输出该标识符
5. 发送媒体前确认这是用户要求的内容，或是本次任务需要交付的最终结果；中间产物、分析输入和未被要求展示的媒体不要发送
6. 回复结束前检查：除非属于上述发送/交付场景，否则删除回复中的所有图片和视频标识符
7. 图片标识符格式为 <user_image_N> 或 <ai_image_N>，视频标识符格式为 <user_video_N> 或 <ai_video_N>

当需要向用户 @某人或戳一戳时，请遵循以下规则：

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

    def rollback_messages(self, count: int) -> Tuple[int, int]:
        """回溯最近 count 轮对话，返回 (删除的消息数, 实际回溯轮数)

        以 user 消息为界划分轮次：删除最近 count 条 user 消息及其后的所有消息。
        """
        user_indices = [i for i, m in enumerate(self.messages) if m.get("role") == "user"]
        if not user_indices:
            return 0, 0
        actual = min(count, len(user_indices))
        cut_idx = user_indices[-actual]
        deleted = len(self.messages) - cut_idx
        del self.messages[cut_idx:]
        self.last_active = time.time()
        self.save_snapshot()
        return deleted, actual

    def _snapshot_path(self) -> Path:
        return self._session_dir / "session.json"

    @classmethod
    def _snapshot_value(cls, value: Any) -> Any:
        """将消息转换为有界 JSON 值，避免快照包含运行时对象或超大内联媒体。"""
        if isinstance(value, str):
            sanitized = cls.INLINE_MEDIA_PATTERN.sub(
                "[inline media omitted from persisted session]", value
            )
            if len(sanitized) > cls.MAX_PERSISTED_STRING_LENGTH:
                return sanitized[:cls.MAX_PERSISTED_STRING_LENGTH] + "...[truncated]"
            return sanitized
        if isinstance(value, dict):
            return {str(k): cls._snapshot_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._snapshot_value(v) for v in value]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return str(value)[:cls.MAX_PERSISTED_STRING_LENGTH]

    @classmethod
    def _recover_messages(cls, messages: Any) -> List[Dict[str, Any]]:
        """恢复消息并丢弃快照末尾未完成的 tool calling 回合。"""
        if not isinstance(messages, list):
            return []
        recovered: List[Dict[str, Any]] = []
        for message in messages[-cls.MAX_PERSISTED_MESSAGES:]:
            if not isinstance(message, dict) or not message.get("role"):
                continue
            recovered.append(copy.deepcopy(message))

        # 历史长度裁剪可能从 tool 响应中间切入，孤立 tool 消息不能提交给下一次 API 请求。
        while recovered and recovered[0].get("role") == "tool":
            recovered.pop(0)

        # 进程可能在工具调用中途退出；这类尾部不能作为下一次 API 请求的历史。
        pending_call_ids: Set[str] = set()
        cut_at: Optional[int] = None
        for index, message in enumerate(recovered):
            if message.get("role") == "assistant" and message.get("tool_calls"):
                pending_call_ids = {
                    str(call.get("id"))
                    for call in message.get("tool_calls", [])
                    if isinstance(call, dict) and call.get("id")
                }
                cut_at = index
            elif message.get("role") == "tool" and pending_call_ids:
                pending_call_ids.discard(str(message.get("tool_call_id", "")))
                if not pending_call_ids:
                    cut_at = None
            elif pending_call_ids and message.get("role") != "tool":
                break
        if pending_call_ids and cut_at is not None:
            recovered = recovered[:cut_at]
        return recovered

    def _load_snapshot(self) -> None:
        """加载持久化快照；损坏或旧版本快照按空会话处理。"""
        path = self._snapshot_path()
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8") as handle:
                snapshot = json.load(handle)
            if snapshot.get("version") != self.SNAPSHOT_VERSION:
                logger.warning(f"{self._tag} 忽略未知版本会话快照: {path}")
                return
            self.persona = snapshot.get("persona")
            self.messages = self._recover_messages(snapshot.get("messages"))
            self.last_active = float(snapshot.get("last_active", self.last_active))
            self.continuous_mode = bool(snapshot.get("continuous_mode", False))
            self.active_skills = {
                str(name) for name in snapshot.get("active_skills", [])
                if isinstance(name, str)
            }
            self.total_prompt_tokens = int(snapshot.get("total_prompt_tokens", 0) or 0)
            self.total_completion_tokens = int(snapshot.get("total_completion_tokens", 0) or 0)
            self.total_tokens = int(snapshot.get("total_tokens", 0) or 0)
            # 以下运行态明确重置，不从快照恢复。
            self._turn_active = False
            self._turn_id = None
            self._pending_inputs.clear()
            self._turn_sent_images.clear()
        except Exception as exc:
            logger.warning(f"{self._tag} 加载会话快照失败，将使用空会话: {exc}")

    def save_snapshot(self) -> None:
        """以临时文件原子替换方式保存主会话快照。"""
        if not self.persistent:
            return
        snapshot = {
            "version": self.SNAPSHOT_VERSION,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "group_id": self.group_id,
            "persona": self._snapshot_value(self.persona),
            "messages": self._snapshot_value(self.messages[-self.MAX_PERSISTED_MESSAGES:]),
            "last_active": self.last_active,
            "continuous_mode": self.continuous_mode,
            "active_skills": sorted(self.active_skills),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
        }
        path = self._snapshot_path()
        tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        with self._persistence_lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with tmp_path.open("w", encoding="utf-8") as handle:
                    json.dump(snapshot, handle, ensure_ascii=False, separators=(",", ":"))
                    handle.flush()
                tmp_path.replace(path)
            except Exception as exc:
                logger.warning(f"{self._tag} 保存会话快照失败: {exc}")
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def dispose(self) -> None:
        """统一清理会话资源：整个 session 目录 + MCP 状态 + 会话锁

        删除会话前必须调用（SessionManager._remove_session 已内聚此逻辑）。
        子 Agent 会话在图片重定位/发送完成前不要调用。
        """
        try:
            self._image_store.clear()
        except Exception:
            logger.exception(f"{self._tag} 清理图片缓存失败")

        try:
            self._video_store.clear()
        except Exception:
            logger.exception(f"{self._tag} 清理视频缓存失败")

        self.clear_pending_inputs()
        self.end_turn()

        try:
            self._clear_session_dir()
        except Exception:
            logger.exception(f"{self._tag} 清理会话目录失败")

        mcp_sm = get_mcp_session_manager()
        if mcp_sm is not None:
            try:
                mcp_sm.clear_session(self.session_id)
            except Exception:
                pass

        # 会话锁在会话销毁后不再需要（持锁中的任务持有的仍是原 Lock 引用，安全）
        _session_locks.pop(self.session_id, None)

    def _clear_session_dir(self) -> None:
        """清理当前会话根目录，覆盖媒体、链式状态和临时文件"""
        if self._session_dir.exists():
            shutil.rmtree(self._session_dir)

    @property
    def session_dir(self) -> Path:
        """当前会话的本地文件根目录"""
        return self._session_dir
    
    def is_expired(self) -> bool:
        if conf.session_timeout <= 0:
            return False
        if self.turn_active or self.pending_input_count() > 0:
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
        self.save_snapshot()
        logger.info(f"{self._tag} Session 激活 SKILL: {skill_name}")
        return True, f"SKILL '{skill_name}' 已激活", skill.content
    
    def deactivate_skill(self, skill_name: str) -> bool:
        """停用指定 SKILL"""
        if skill_name in self.active_skills:
            self.active_skills.discard(skill_name)
            self.last_active = time.time()
            self.save_snapshot()
            return True
        return False
    
    def deactivate_all_skills(self) -> None:
        """停用所有 SKILL"""
        self.active_skills.clear()
        self.last_active = time.time()
        self.save_snapshot()
    
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
        self.save_snapshot()
    


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
            if SUBAGENT_TYPES:
                lines = ["【可用的子 Agent 类型】", "使用 delegate_task 工具时，通过 type 参数选择类型："]
                for t in SUBAGENT_TYPES.values():
                    lines.append(f"  · {t.name}: {t.description}")
                context_parts.append("\n".join(lines))

        # 记忆注入（全局 + 用户两层）
        if conf.enable_memory and self.user_id:
            memory_sections: List[str] = []
            try:
                global_text = await memory_store.get_global_inject_text(conf.memory_max_inject_length)
                if global_text:
                    memory_sections.append(f"【全局记忆】\n{global_text}")
            except Exception as e:
                logger.warning(f"[Memory] 注入全局记忆失败: {e}")
            try:
                memory_text = await memory_store.get_inject_text(self.user_id, conf.memory_max_inject_length)
                if memory_text:
                    memory_sections.append(f"【关于该用户的历史记忆】\n{memory_text}")
                    logger.debug(f"{self._tag} [Memory] 已注入记忆，长度: {len(memory_text)}")
            except Exception as e:
                logger.warning(f"[Memory] 注入记忆失败: {e}")
            if memory_sections:
                context_parts.append("\n\n".join(memory_sections))

        context_msgs: List[Dict[str, Any]] = []
        if context_parts:
            context_text = "\n\n".join(p for p in context_parts if p)
            context_msgs = [
                {"role": "user", "content": context_text},
                {"role": "assistant", "content": "已了解当前系统上下文。"},
            ]

        # 3. 用户媒体锚定：历史中已由 chat.py 插入独立的"用户发送了图片/视频"消息，
        #    不再需要动态附加清单（LLM 能力已可直接按编号引用）。仅浅拷贝历史。
        api_messages = [_copy_message(m) for m in self.messages]

        # 调试日志
        system_log = system_content[:2000] + "...[截断]" if len(system_content) > 2000 else system_content
        logger.debug(f"[SKILL] 完整系统消息:\n{system_log}")

        # 4. 返回完整 API 消息（system + context + 历史副本）
        return [system_msg] + context_msgs + api_messages
    


class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self._gc_task: Optional[asyncio.Task] = None

    # ========== 生命周期 GC ==========

    def start_gc(self, interval: int = 300) -> None:
        """启动周期 GC 任务（幂等），清理过期会话"""
        if self._gc_task is not None and not self._gc_task.done():
            return
        self._gc_task = asyncio.create_task(self._gc_loop(interval))
        logger.info(f"Session GC 已启动，间隔 {interval}s")

    async def stop_gc(self) -> None:
        if self._gc_task is not None and not self._gc_task.done():
            self._gc_task.cancel()
            try:
                await self._gc_task
            except asyncio.CancelledError:
                pass
        self._gc_task = None

    async def _gc_loop(self, interval: int) -> None:
        while True:
            await asyncio.sleep(interval)
            self._sweep()

    def _sweep(self) -> int:
        """清理过期的用户会话；任务会话（bg/sub/agent）由各自 finally 自清理，跳过"""
        removed = 0
        for session_id in list(self.sessions.keys()):
            if not (session_id.startswith("group_") or session_id.startswith("private_")):
                continue
            session = self.sessions[session_id]
            if session.is_expired():
                logger.info(f"[GC] 清理过期会话 {session_id}")
                self._remove_session(session_id)
                removed += 1

        # 重启后尚未懒加载到内存的主会话也需要遵守 session_timeout。
        base_dir = ImageStoreCore.BASE_DIR.resolve()
        if conf.session_timeout > 0 and base_dir.exists():
            for session_dir in base_dir.iterdir():
                if not session_dir.is_dir() or not (
                    session_dir.name.startswith("group_")
                    or session_dir.name.startswith("private_")
                ):
                    continue
                if session_dir.name in self.sessions:
                    continue
                snapshot_path = session_dir / "session.json"
                if not snapshot_path.exists():
                    continue
                try:
                    with snapshot_path.open("r", encoding="utf-8") as handle:
                        snapshot = json.load(handle)
                    last_active = float(snapshot.get("last_active", 0))
                    if last_active and time.time() - last_active > conf.session_timeout:
                        shutil.rmtree(session_dir)
                        removed += 1
                        logger.info(f"[GC] 清理磁盘中的过期会话 {session_dir.name}")
                except Exception as exc:
                    logger.warning(f"[GC] 检查磁盘会话失败 {session_dir.name}: {exc}")
        return removed

    def get_session_id(self, user_id: int, group_id: Optional[int] = None) -> str:
        if group_id:
            return f"group_{group_id}_user_{user_id}"
        return f"private_{user_id}"
    
    def _remove_session(self, session_id: str) -> None:
        """统一删除 session 入口，资源清理内聚到 Session.dispose()"""
        session = self.sessions.pop(session_id, None)
        if session is not None:
            logger.debug(f"[_remove_session] session={session_id} 已从内存中删除")
            session.dispose()
    
    def get_session(self, user_id: int, group_id: Optional[int] = None) -> Optional[Session]:
        """获取已存在且未过期的 session，不存在或过期返回 None"""
        session_id = self.get_session_id(user_id, group_id)
        session = self.sessions.get(session_id)
        if session is None:
            snapshot_path = ImageStoreCore._resolve_session_dir(session_id) / "session.json"
            if snapshot_path.exists():
                session = Session(
                    session_id,
                    user_id,
                    group_id=group_id,
                    register=True,
                    persistent=True,
                    load_existing=True,
                )
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
        else:
            # 内存已重启但磁盘仍有旧快照时，显式新建代表用户要求重置会话。
            session_dir = ImageStoreCore._resolve_session_dir(session_id)
            if session_dir.exists():
                shutil.rmtree(session_dir)
        session = Session(
            session_id,
            user_id,
            persona=persona,
            group_id=group_id,
            persistent=True,
        )
        self.sessions[session_id] = session
        session.save_snapshot()
        return session
    
    def get_or_create_session(self, user_id: int, group_id: Optional[int] = None,
                              persona: Optional[str] = None) -> Session:
        """获取已存在的 session，不存在则创建"""
        session = self.get_session(user_id, group_id)
        if not session:
            session = self.create_session(user_id, group_id, persona)
        return session
    
    def clear_session(self, user_id: int, group_id: Optional[int] = None) -> bool:
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            self._remove_session(session_id)
            return True
        session_dir = ImageStoreCore._resolve_session_dir(session_id)
        if session_dir.exists():
            try:
                shutil.rmtree(session_dir)
                return True
            except Exception as exc:
                logger.warning(f"清理磁盘会话失败 {session_id}: {exc}")
        return False


session_manager = SessionManager()
