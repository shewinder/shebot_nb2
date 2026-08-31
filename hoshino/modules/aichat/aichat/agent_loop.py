"""AgentLoop — 隔离会话执行的统一编排器

取代 _agent_runner.run_agent：delegate_task / 后台任务 / 定时任务
三条路径共用 AgentTask 规格与 run_agent_loop 实现。

职责边界：只做"会话创建/提示注入/图片传递/清理"的编排，
工具循环与 usage 记账仍由 ChatExecutor 负责。

设计要点（见 docs/p2-agent-loop-design.md）：
- session_id 追加 uuid 后缀，根治同前缀并行任务互相覆盖的竞态；
- finally 中用 is 校验实例后才解除注册，双保险；
- AgentResult 保留已解注册的子会话对象，供调用方发图/重定位/dispose。
"""
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger
from pydantic import BaseModel, ConfigDict, field_validator

from .api import _build_api_config_dict, api_manager
from .chat_executor import ChatExecutor, ChatResult
from .config import Config
from .infra import AppError
from .reply import IMAGE_TOKEN_RE
from .session import Session, session_manager

conf = Config.get_instance('aichat')


class AgentTask(BaseModel):
    """一次隔离 Agent 执行的完整规格

    tools: None=自动全量（受 blocked_tools 过滤）；[]=无工具；否则白名单
    session_prefix: 仅语义前缀（bg_task_ / agent_task_ / subagent_），
        真实 session_id 会追加随机后缀，前缀语义（如 wait_and_resume 可见性）保留。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task: str
    system_prompt: str
    user_id: int
    group_id: Optional[int] = None
    tools: Optional[List[Dict[str, Any]]] = None
    max_rounds: int = 10
    profile: Optional[str] = None
    persona: Optional[str] = None
    image_identifiers: List[str] = field(default_factory=list)
    # 一次性多模态输入：不写入 ImageStore，不产生可发送的图片标识符
    image_data_urls: List[str] = field(default_factory=list)
    parent_session: Optional[Session] = None
    preactivate_skills: List[str] = field(default_factory=list)
    blocked_tools: frozenset = field(default_factory=frozenset)
    locked_tools: bool = False
    session_prefix: str = "agent"
    label: str = "sub"
    api_config: Optional[Dict[str, Any]] = None

    @field_validator("task")
    @classmethod
    def _strip_task(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("task 不能为空")
        return v

    @field_validator("max_rounds")
    @classmethod
    def _clamp_max_rounds(cls, v: int) -> int:
        return max(1, min(int(v), conf.max_tool_rounds))


@dataclass
class AgentResult:
    """AgentLoop 执行结果：ChatResult + 已解注册但仍可用的子会话"""

    result: ChatResult
    session: Session
    # 图片复制溯源映射：{子会话标识符: 父会话原始标识符}，供 rehome 零拷贝重写
    image_map: Dict[str, str] = field(default_factory=dict)


def _resolve_api_config(profile: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """解析子 Agent 的 API 配置

    优先级：profile 匹配 > subagent_profiles[0] 默认 > 主 API。
    注意：subagent_profiles[0] 回落是既有行为（影响 bg/scheduled 的 API 归属），
    本轮保持对齐，不改变。
    """
    api_config = api_manager.get_api_config()
    if not api_config:
        return None

    target = None
    for p in conf.subagent_profiles:
        if profile and p.name == profile:
            target = p
            break
    if not target and conf.subagent_profiles:
        target = conf.subagent_profiles[0]

    if target and target.api:
        entry = conf.get_api_by_name(target.api)
        if entry:
            api_dict = _build_api_config_dict(entry)
            if target.model:
                api_dict["model"] = target.model
            if target.supports_multimodal is not None:
                api_dict["supports_multimodal"] = target.supports_multimodal
            return api_dict

    return api_config


async def _copy_images_with_map(
    sub_session: Session,
    parent_session: Session,
    identifiers: List[str],
) -> Tuple[List[str], Dict[str, str]]:
    """将父会话图片复制到子会话，返回 (子标识符列表, 溯源映射)"""
    new_ids: List[str] = []
    image_map: Dict[str, str] = {}
    for ident in identifiers:
        data_url = parent_session._image_store.get_data_url(ident)
        if data_url:
            entry = parent_session._image_store.get(ident)
            source_url = entry.url if entry else None
            new_id = await sub_session.store_user_image(data_url, url=source_url)
            new_ids.append(new_id)
            image_map[new_id] = ident
    return new_ids, image_map


def _build_multimodal_message(
    text: str,
    identifiers: List[str],
    session: Session,
    image_data_urls: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """构建多模态消息内容（文本 + 持久或一次性图片 data_url）"""
    content: List[Dict[str, Any]] = []
    for data_url in image_data_urls or []:
        if data_url:
            content.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })
    for ident in identifiers:
        data_url = session._image_store.get_data_url(ident)
        if data_url:
            content.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })
    if text:
        content.append({"type": "text", "text": text})
    elif not content:
        content.append({"type": "text", "text": text})
    return content


async def run_agent_loop(task: AgentTask) -> AgentResult:
    """在独立 Session 中执行一个 Agent 任务"""
    session_id = f"{task.session_prefix}_{uuid.uuid4().hex[:8]}"
    session = Session(
        session_id,
        task.user_id,
        persona=task.persona,
        group_id=task.group_id,
        register=True,
    )
    session.agent_label = task.label
    if task.locked_tools:
        session._subagent_locked_tools = True
    session._blocked_tools = task.blocked_tools

    try:
        return await _run(task, session)
    finally:
        # 无论成功/异常都解除注册；仅当注册表中仍是自己时才删除
        _unregister(session_id, session)


async def _run(task: AgentTask, session: Session) -> AgentResult:
    api_config = task.api_config or _resolve_api_config(task.profile)
    if not api_config or not api_config.get("api_key"):
        logger.error(f"[Agent:{task.label}] API 未配置，无法执行子任务")
        return AgentResult(
            result=ChatResult(error=AppError("API 未配置", code="llm.unconfigured")),
            session=session,
        )

    # 预激活 SKILL，省去首轮 activate_skill 调用
    if task.preactivate_skills:
        for skill_name in task.preactivate_skills:
            ok_flag, msg, _ = session.activate_skill(skill_name)
            if ok_flag:
                logger.info(f"[Agent:{task.label}] 预激活 SKILL: {skill_name}")
            else:
                logger.warning(f"[Agent:{task.label}] 预激活 SKILL 失败: {skill_name} — {msg}")

    session.add_message("system", task.system_prompt)

    # 构建 user 消息：支持多模态图片传递
    new_ids: List[str] = []
    image_map: Dict[str, str] = {}
    if task.image_identifiers and task.parent_session:
        new_ids, image_map = await _copy_images_with_map(
            session, task.parent_session, task.image_identifiers
        )

    supports_multimodal = api_config.get("supports_multimodal", False)
    if task.image_data_urls and not supports_multimodal:
        return AgentResult(
            result=ChatResult(
                error=AppError("视觉模型未开启多模态，无法分析视频帧", code="llm.multimodal_unavailable")
            ),
            session=session,
            image_map=image_map,
        )

    if (new_ids or task.image_data_urls) and supports_multimodal:
        message_content = _build_multimodal_message(
            task.task,
            new_ids,
            session,
            image_data_urls=task.image_data_urls,
        )
        session.add_message("user", message_content)
    else:
        prompt = task.task
        if new_ids:
            prompt = f"{task.task}\n\n图片标识符：{' '.join(new_ids)}"
        session.add_message("user", prompt)

    result = await ChatExecutor(session).chat(
        api_config=api_config,
        tools=task.tools,
        max_rounds=task.max_rounds,
    )
    return AgentResult(result=result, session=session, image_map=image_map)


def _unregister(session_id: str, session: Session) -> None:
    """解除注册；仅当注册表中仍是我们自己的实例时才删除（防误删他人任务）"""
    if session_manager.sessions.get(session_id) is session:
        session_manager.sessions.pop(session_id, None)


# ========== 图片重定位 ==========


async def _copy_image_to_parent(
    child: Session, parent: Session, identifier: str
) -> Optional[str]:
    """把子会话图片拷贝到父会话，返回父会话新标识符；失败返回 None"""
    data_url = child._image_store.get_data_url(identifier)
    if not data_url:
        return None
    entry = child._image_store.get(identifier)
    url = entry.url if entry else None
    source = entry.source if entry else "ai"
    if source == "user":
        return await parent.store_user_image(data_url, url=url)
    return await parent.store_ai_image(data_url, url=url)


async def _rehome_one(
    agent_result: AgentResult, parent: Session, identifier: str
) -> str:
    """重定位单个标识符：溯源映射命中 → 零拷贝；否则拷贝；失败降级为占位符"""
    if identifier in agent_result.image_map:
        return agent_result.image_map[identifier]

    new_id = await _copy_image_to_parent(agent_result.session, parent, identifier)
    if new_id:
        return new_id

    logger.warning(f"[AgentLoop] 图片重定位失败，降级为占位符: {identifier}")
    return "[图片]"


async def rehome_images(
    agent_result: AgentResult,
    parent: Session,
    *,
    auto_attach: bool = True,
) -> str:
    """把子 Agent 结果文本中的图片标识符重定位到父会话命名空间

    返回重写后的文本。子会话中"本轮创建但未被引用"的 ai 图片
    在 auto_attach=True 时一并拷贝并追加（兜底补发）。
    """
    content = agent_result.result.content or ""
    child = agent_result.session
    referenced: Set[str] = set()

    parts: List[str] = []
    pos = 0
    for m in IMAGE_TOKEN_RE.finditer(content):
        parts.append(content[pos:m.start()])
        norm = f"<{m.group(1)}>"
        parts.append(await _rehome_one(agent_result, parent, norm))
        referenced.add(norm)
        pos = m.end()
    parts.append(content[pos:])
    content = "".join(parts)

    if auto_attach:
        threshold = getattr(child, "last_user_msg_at", 0.0)
        extra: List[str] = []
        for img in child._image_store.list_all():
            if img.source != "ai" or img.created_at < threshold:
                continue
            if img.identifier in referenced:
                continue
            new_id = await _copy_image_to_parent(child, parent, img.identifier)
            if new_id:
                extra.append(new_id)
        if extra:
            content = (content.rstrip() + "\n" + " ".join(extra)) if content else " ".join(extra)

    return content
