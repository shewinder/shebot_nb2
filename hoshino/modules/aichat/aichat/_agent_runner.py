"""独立 Agent 执行器

为 delegate_task、background_task、scheduled_task 提供统一的
"创建隔离 Session → 注入提示 → ChatExecutor 执行" 流程。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

from .api import api_manager, _build_api_config_dict
from .config import Config
from .session import Session, session_manager

if TYPE_CHECKING:
    from .session import Session as SessionType

conf = Config.get_instance('aichat')


@dataclass(frozen=True)
class SubAgentTypeDef:
    name: str
    description: str       # 给 AI 看，用于选择类型
    system_prompt: str     # 子 Agent 的 system prompt
    tool_names: frozenset[str] = field(default_factory=frozenset)


SUBAGENT_TYPES: Dict[str, SubAgentTypeDef] = {
    "search": SubAgentTypeDef(
        name="search",
        description="搜索汇总：联网搜索、抓取网页、收集分析信息",
        system_prompt="""【搜索汇总模式】
你是主 Agent 派出的搜索子 Agent，负责独立完成信息搜索与汇总任务并汇报结果。

执行规则：
- 直接执行任务，不要反问或等待用户确认
- 如果用户消息中包含图片，你可以直接看到并分析
- 使用 web_search 和 fetch_url 全面收集信息
- 完成后返回清晰的结构化结果摘要
- 简洁直接，不添加无关评论或角色扮演
- 如果任务无法完成，明确说明原因及已尝试的步骤""",
        tool_names=frozenset({"web_search", "fetch_url", "get_current_time", "weather"}),
    ),
    "vision": SubAgentTypeDef(
        name="vision",
        description="视觉分析：看图、识图、分析图片内容",
        system_prompt="""【视觉分析模式】
你是主 Agent 派出的视觉分析子 Agent，负责独立完成图片/视觉内容分析任务并汇报结果。

执行规则：
- 直接执行任务，不要反问或等待用户确认
- 你可以直接看到并分析用户提供的图片（具有多模态视觉能力）
- 完成后返回清晰的结构化分析结果
- 简洁直接，不添加无关评论或角色扮演
- 如果任务无法完成，明确说明原因及已尝试的步骤""",
        tool_names=frozenset({"fetch_url"}),
    ),
}


def _resolve_api_config(profile_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """解析子 Agent 的 API 配置

    优先级：profile 匹配 > subagent_profiles[0] 默认 > 主 API
    """
    api_config = api_manager.get_api_config()
    if not api_config:
        return None

    target = None
    for p in conf.subagent_profiles:
        if profile_name and p.name == profile_name:
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


async def _copy_images(
    sub_session: Session,
    parent_session: "SessionType",
    identifiers: List[str],
) -> List[str]:
    """将父 Session 的图片复制到子 Session，返回新标识符列表"""
    new_ids = []
    for ident in identifiers:
        data_url = parent_session._image_store.get_data_url(ident)
        if data_url:
            entry = parent_session._image_store.get(ident)
            source_url = entry.url if entry else None
            new_id = await sub_session.store_user_image(data_url, url=source_url)
            new_ids.append(new_id)
    return new_ids


def _build_multimodal_message(
    text: str, identifiers: List[str], session: Session
) -> List[Dict[str, Any]]:
    """构建多模态消息内容（文本 + 图片 data_url）"""
    content: List[Dict[str, Any]] = []
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


async def run_agent(
    task: str,
    system_prompt: str,
    user_id: int,
    group_id: Optional[int] = None,
    *,
    tools: Optional[List[Dict[str, Any]]] = None,
    persona: Optional[str] = None,
    max_rounds: int = 5,
    locked_tools: bool = False,
    blocked_tools: frozenset = frozenset(),
    preactivate_skills: Optional[List[str]] = None,
    session_prefix: str = "agent",
    api_config: Optional[Dict[str, Any]] = None,
    profile: Optional[str] = None,
    parent_session: Optional["SessionType"] = None,
    image_identifiers: Optional[List[str]] = None,
):
    """在独立 Session 中运行一个 Agent 任务

    Args:
        profile: 子 Agent 模型配置名
        parent_session: 父 Session（用于传递图片等资源）
        image_identifiers: 需传递给子 Agent 的图片标识符列表
        blocked_tools: 禁止 sub agent 使用的工具名集合
        preactivate_skills: 预激活的 SKILL 名称列表，省去首轮 activate_skill 调用
    """
    from .chat_executor import ChatExecutor, ChatResult

    if profile:
        api_config = _resolve_api_config(profile)
    elif api_config is None:
        api_config = _resolve_api_config(None)
    if not api_config or not api_config.get("api_key"):
        return ChatResult(error="API 未配置")

    label = f"sub:{profile}" if profile else "sub"
    session = Session(
        f"{session_prefix}_{user_id}",
        user_id,
        persona=persona,
        group_id=group_id,
        register=True,
    )
    session.agent_label = label
    if locked_tools:
        session._subagent_locked_tools = True
    session._blocked_tools = blocked_tools

    # 预激活 SKILL，省去 sub agent 首轮调 activate_skill
    if preactivate_skills:
        for skill_name in preactivate_skills:
            ok_flag, msg, _ = session.activate_skill(skill_name)
            if ok_flag:
                logger.info(f"[Agent:sub] 预激活 SKILL: {skill_name}")
            else:
                logger.warning(f"[Agent:sub] 预激活 SKILL 失败: {skill_name} — {msg}")

    session.add_message("system", system_prompt)

    # 构建 user 消息：支持多模态图片传递
    supports_multimodal = api_config.get("supports_multimodal", False)
    new_ids: List[str] = []

    if image_identifiers and parent_session:
        new_ids = await _copy_images(session, parent_session, image_identifiers)

    if new_ids and supports_multimodal:
        # 多模态模式：图片嵌入消息内容
        message_content = _build_multimodal_message(task, new_ids, session)
        session.add_message("user", message_content)
    else:
        # 纯文本模式
        prompt = task
        if new_ids:
            prompt = f"{task}\n\n图片标识符：{' '.join(new_ids)}"
        session.add_message("user", prompt)

    try:
        return await ChatExecutor(session).chat(
            api_config=api_config,
            tools=tools,
            max_rounds=max_rounds,
        )
    finally:
        session_manager.sessions.pop(session.session_id, None)
