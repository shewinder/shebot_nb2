"""同步委托子 Agent 工具

为 AI 提供 delegate_task 工具，可将复杂子任务委托给独立的子 Agent 执行。
子 Agent 拥有独立 Session、受限工具集和任务专用 system prompt，
执行完毕后返回摘要，不污染主对话上下文。

子 Agent 类型（代码写死）：
- search: 搜索汇总（web_search, fetch_url, get_current_time, weather）
- vision: 视觉分析（fetch_url）

模型配置、工具白名单覆盖、max_rounds 覆盖在 SubAgentProfile 中配置。
"""
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

from ..._agent_runner import run_agent, SUBAGENT_TYPES
from ...config import Config
from ..registry import tool_registry, ok, fail

if TYPE_CHECKING:
    from ...session import Session

conf = Config.get_instance('aichat')


def _build_whitelist_tools(tool_names: set) -> List[Dict[str, Any]]:
    """构建子 Agent 工具列表（白名单过滤）"""
    tools = []
    for name in tool_names:
        tool_info = tool_registry.get_tool_info(name)
        if tool_info:
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_info.name,
                    "description": tool_info.description,
                    "parameters": tool_info.parameters,
                }
            })
    return tools


def _build_type_descriptions() -> str:
    """构建子 Agent 类型描述列表（注入主 Agent 提示）"""
    lines = []
    for t in SUBAGENT_TYPES.values():
        lines.append(f"  · {t.name}: {t.description}")
    return "\n".join(lines)


@tool_registry.register(
    name="delegate_task",
    description="""【同步委托】将子任务交给独立的子 Agent 执行，等待完成后返回结果。

子 Agent 拥有独立的对话上下文和受限工具集，执行过程不污染你的主对话上下文。
适合需要多轮搜索、信息收集、分析的复杂查询，以及图片/视觉内容分析。

## 何时使用
- 需要深入搜索多个关键词收集信息 → type="search"
- 需要分析图片/视觉内容 → type="vision"
- 多个独立的子任务（可在同一轮并行调用多个 delegate_task）

## 何时不用
- 简单的一步操作（直接用对应工具）
- 需要与用户交互的场景（子 Agent 无法看到用户消息）
- 需要操作文件、执行脚本或有副作用的操作

## 使用技巧
- 任务描述要具体明确，包含预期产出
- 多个独立查询可以并行委托（同一轮中调用本工具多次）
- 子 Agent 返回后，你基于摘要合成最终回复""",
    parameters={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "子任务的详细描述，说明要研究/分析/收集什么，期望的产出格式"
            },
            "type": {
                "type": "string",
                "description": "子 Agent 类型，从系统提示中列出的可用类型中选择。如 'search'（搜索汇总）、'vision'（视觉分析）"
            },
            "image_identifiers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "需传递给子 Agent 的图片标识符列表，如 [\"user_image_1\", \"ai_image_3\"]。需要子 Agent 分析图片时传入"
            },
            "preactivate_skills": {
                "type": "array",
                "items": {"type": "string"},
                "description": "预激活的 SKILL 名称列表。传入 sub agent 执行任务需要用到的 SKILL，避免首轮再调 activate_skill。"
            },
        },
        "required": ["task"]
    },
)
async def delegate_task(
    task: str,
    session: Optional["Session"] = None,
    type: str = "search",
    image_identifiers: Optional[List[str]] = None,
    preactivate_skills: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """同步委托子 Agent 执行任务"""
    if not session:
        return fail("无法获取会话上下文", error="Missing session")

    if not task or not task.strip():
        return fail("任务描述不能为空")

    task = task.strip()
    agent_type = type.strip() if type else "search"

    # 解析类型定义
    type_def = SUBAGENT_TYPES.get(agent_type)
    if not type_def:
        available = ", ".join(SUBAGENT_TYPES.keys())
        return fail(f"未知的子 Agent 类型: {agent_type}，可用类型: {available}")

    # 查找匹配的配置 profile（按名称匹配，用于覆盖模型/工具/轮数）
    config_profile = None
    for p in conf.subagent_profiles:
        if p.name == agent_type:
            config_profile = p
            break

    # 工具白名单：配置覆盖 > 类型默认
    if config_profile and config_profile.tool_names:
        tool_names = set(config_profile.tool_names)
    else:
        tool_names = set(type_def.tool_names)

    # max_rounds：配置覆盖 > 全局默认
    max_rounds = None
    if config_profile and config_profile.max_rounds is not None:
        max_rounds = config_profile.max_rounds
    else:
        max_rounds = getattr(conf, 'subagent_max_rounds', 5)

    tools = _build_whitelist_tools(tool_names)

    logger.info(
        f"[SubAgent] 开始子任务，type={agent_type}，"
        f"任务长度: {len(task)}，工具: {tool_names}，max_rounds: {max_rounds}"
    )

    try:
        result = await run_agent(
            task=task,
            system_prompt=type_def.system_prompt,
            user_id=session.user_id,
            group_id=session.group_id,
            tools=tools,
            max_rounds=max_rounds,
            locked_tools=True,
            session_prefix=f"subagent_{session.session_id}",
            profile=agent_type,
            parent_session=session,
            image_identifiers=image_identifiers,
            blocked_tools=frozenset({"run_background_task", "delegate_task", "schedule_task"}),
            preactivate_skills=preactivate_skills,
        )

        content = result.content or ""
        rounds = len(result.tool_results)

        if result.error and not content:
            logger.warning(f"[SubAgent] 子任务失败: {result.error}")
            return fail(f"子任务执行失败: {result.error}", error=result.error)

        if result.error:
            logger.warning(f"[SubAgent] 子任务部分完成: {result.error}")

        logger.info(f"[SubAgent] 子任务完成，{rounds} 轮工具调用，结果长度: {len(content)}")
        return ok(
            content,
            metadata={
                "type": agent_type,
                "rounds": rounds,
                "task": task[:100],
                "partial": bool(result.error),
            }
        )

    except Exception as e:
        logger.exception(f"[SubAgent] 子任务异常: {e}")
        return fail(f"子任务执行异常: {str(e)}", error=str(e))
