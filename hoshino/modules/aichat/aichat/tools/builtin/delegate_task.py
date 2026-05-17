"""同步委托子 Agent 工具

为 AI 提供 delegate_task 工具，可将复杂子任务委托给独立的子 Agent 执行。
子 Agent 拥有独立 Session、受限工具集和任务专用 system prompt，
执行完毕后返回摘要，不污染主对话上下文。
"""
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

from ..registry import tool_registry, ok, fail
from ...config import Config

if TYPE_CHECKING:
    from ...session import Session

conf = Config.get_instance('aichat')

# 子 Agent 可用工具白名单（只读、非破坏性）
_SUBAGENT_TOOLS = {"web_search", "fetch_url", "get_current_time", "weather"}

# 子 Agent 系统提示
_SUBAGENT_SYSTEM_PROMPT = """【子任务执行模式】
你是主 Agent 派出的子 Agent，负责独立完成一个具体任务并汇报结果。

执行规则：
- 直接执行任务，不要反问或等待用户确认
- 使用可用工具收集信息，必要时多轮搜索
- 完成后返回清晰的结构化结果摘要
- 简洁直接，不添加无关评论或角色扮演
- 如果任务无法完成，明确说明原因及已尝试的步骤"""


def _build_subagent_tools() -> List[Dict[str, Any]]:
    """构建子 Agent 工具列表（白名单过滤）"""
    from ...tools.registry import tool_registry as registry

    tools = []
    for name in _SUBAGENT_TOOLS:
        tool_info = registry.get_tool_info(name)
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


async def _run_subagent(
    task: str,
    session: "Session",
    api_config: Dict[str, Any],
) -> Dict[str, Any]:
    """在独立 Session 中执行子 Agent 任务，返回结果"""
    from ...session import Session
    from ...chat_executor import ChatExecutor

    subagent_tools = _build_subagent_tools()
    if not subagent_tools:
        return {"success": False, "content": "", "error": "子 Agent 无可用的工具"}

    # 创建独立子 Session
    sub_session = Session(
        f"subagent_{session.session_id}",
        session.user_id,
        group_id=session.group_id,
    )
    sub_session._subagent_locked_tools = True  # 锁定工具集，阻止每轮重新加载

    # 只注入系统提示和任务，不注入角色设定
    sub_session.add_message("system", _SUBAGENT_SYSTEM_PROMPT)
    sub_session.add_message("user", task)

    # 用独立 ChatExecutor 执行
    executor = ChatExecutor(sub_session)

    # 子 Agent 的 API 配置：缩减工具调用轮数
    sub_api_config = dict(api_config)
    sub_api_config["supports_tools"] = True

    max_rounds = getattr(conf, 'subagent_max_rounds', 5)

    result = await executor._chat_with_api(
        messages=await sub_session._build_messages_for_chat(),
        api_config=sub_api_config,
        tools=subagent_tools,
        max_tool_rounds=max_rounds,
    )

    return {
        "success": not result.error,
        "content": result.content or "",
        "error": result.error,
        "tool_rounds": len(result.tool_results),
    }


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
- 子 Agent 返回后，你基于摘要合成最终回复""",
    parameters={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "子任务的详细描述，说明要研究/分析/收集什么，期望的产出格式"
            },
        },
        "required": ["task"]
    },
)
async def delegate_task(
    task: str,
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    """同步委托子 Agent 执行任务

    Args:
        task: 任务描述
        session: 主对话 Session（自动注入）

    Returns:
        子 Agent 的执行结果
    """
    if not session:
        return fail("无法获取会话上下文", error="Missing session")

    if not task or not task.strip():
        return fail("任务描述不能为空")

    task = task.strip()

    # 获取 API 配置
    from ...api import api_manager
    api_config = api_manager.get_api_config()
    if not api_config or not api_config.get("api_key"):
        return fail("API 未配置，无法执行子任务")

    logger.info(f"[SubAgent] 开始执行子任务，长度: {len(task)}，会话: {session.session_id[:30]}...")

    try:
        result = await _run_subagent(task, session, api_config)

        if result["success"]:
            content = result["content"]
            rounds = result.get("tool_rounds", 0)
            logger.info(f"[SubAgent] 子任务完成，{rounds} 轮工具调用，结果长度: {len(content)}")
            return ok(
                content,
                metadata={
                    "rounds": rounds,
                    "task": task[:100],
                }
            )
        else:
            error = result.get("error", "未知错误")
            content = result.get("content", "")
            logger.warning(f"[SubAgent] 子任务失败: {error}，部分结果长度: {len(content)}")
            if content:
                return ok(
                    f"子任务部分完成（遇到错误：{error}）：\n\n{content}",
                    metadata={"partial": True, "error": error}
                )
            return fail(f"子任务执行失败: {error}", error=error)

    except Exception as e:
        logger.exception(f"[SubAgent] 子任务异常: {e}")
        return fail(f"子任务执行异常: {str(e)}", error=str(e))
