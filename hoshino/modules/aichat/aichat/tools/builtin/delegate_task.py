"""同步委托子 Agent 工具

为 AI 提供 delegate_task 工具，可将复杂子任务委托给独立的子 Agent 执行。
子 Agent 拥有独立 Session、受限工具集和任务专用 system prompt，
执行完毕后返回摘要，不污染主对话上下文。
"""
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

from ..._agent_runner import run_agent
from ...config import Config
from ..registry import tool_registry, ok, fail

if TYPE_CHECKING:
    from ...session import Session

conf = Config.get_instance('aichat')

# 子 Agent 系统提示
_SUBAGENT_SYSTEM_PROMPT = """【子任务执行模式】
你是主 Agent 派出的子 Agent，负责独立完成一个具体任务并汇报结果。

执行规则：
- 直接执行任务，不要反问或等待用户确认
- 使用可用工具收集信息，必要时多轮搜索
- 完成后返回清晰的结构化结果摘要
- 简洁直接，不添加无关评论或角色扮演
- 如果任务无法完成，明确说明原因及已尝试的步骤"""

# 子 Agent 可用工具白名单（只读、非破坏性）
_SUBAGENT_TOOL_NAMES = {"web_search", "fetch_url", "get_current_time", "weather"}


def _build_whitelist_tools() -> List[Dict[str, Any]]:
    """构建子 Agent 工具列表（白名单过滤）"""
    tools = []
    for name in _SUBAGENT_TOOL_NAMES:
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


@tool_registry.register(
    name="delegate_task",
    description="""【同步委托】将子任务交给独立的子 Agent 执行，等待完成后返回结果。

子 Agent 拥有独立的对话上下文和受限工具集（web_search、fetch_url、get_current_time、weather），
执行过程不污染你的主对话上下文。适合需要多轮搜索、信息收集、分析的复杂查询。

## 何时使用
- 需要深入搜索多个关键词收集信息
- 需要抓取多个网页并综合内容
- 需要独立完成一个信息收集/分析子任务
- 多个独立的子任务（可在同一轮并行调用多个 delegate_task）

## 何时不用
- 简单的一步操作（直接用对应工具）
- 需要与用户交互的场景（子 Agent 无法看到用户消息）
- 需要操作文件、执行脚本或有副作用的操作

## 使用技巧
- 任务描述要具体明确，包含预期产出
- 多个独立查询可以并行委托（同一轮中调用本工具多次）
- 子 Agent 返回后，你基于摘要合成最终回复
- 系统提示中如果列出了可用的子 Agent 模型配置，可根据任务类型选择对应的 profile""",
    parameters={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "子任务的详细描述，说明要研究/分析/收集什么，期望的产出格式"
            },
            "profile": {
                "type": "string",
                "description": "子 Agent 模型配置名。根据系统提示中的可用配置选择，不传则使用默认"
            },
            "image_identifiers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "需传递给子 Agent 的图片标识符列表，如 [\"user_image_1\", \"ai_image_3\"]。需要子 Agent 分析图片时传入"
            },
        },
        "required": ["task"]
    },
)
async def delegate_task(
    task: str,
    session: Optional["Session"] = None,
    profile: str = "",
    image_identifiers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """同步委托子 Agent 执行任务"""
    if not session:
        return fail("无法获取会话上下文", error="Missing session")

    if not task or not task.strip():
        return fail("任务描述不能为空")

    task = task.strip()
    profile_name = profile.strip() if profile else ""

    logger.info(f"[SubAgent] 开始执行子任务，长度: {len(task)}，profile: {profile_name or '默认'}，图片: {len(image_identifiers) if image_identifiers else 0}")

    try:
        result = await run_agent(
            task=task,
            system_prompt=_SUBAGENT_SYSTEM_PROMPT,
            user_id=session.user_id,
            group_id=session.group_id,
            tools=_build_whitelist_tools(),
            max_rounds=getattr(conf, 'subagent_max_rounds', 5),
            locked_tools=True,
            session_prefix=f"subagent_{session.session_id}",
            profile=profile_name or None,
            parent_session=session,
            image_identifiers=image_identifiers,
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
                "rounds": rounds,
                "task": task[:100],
                "partial": bool(result.error),
            }
        )

    except Exception as e:
        logger.exception(f"[SubAgent] 子任务异常: {e}")
        return fail(f"子任务执行异常: {str(e)}", error=str(e))
