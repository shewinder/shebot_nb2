"""子 Agent 类型定义

从 _agent_runner 拆出：类型定义不依赖执行器，
供 session.py（注入主 Agent 提示）与 delegate_task（解析类型）共享。
"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class SubAgentTypeDef:
    name: str
    description: str       # 给 AI 看，用于选择类型
    system_prompt: str     # 子 Agent 的 system prompt
    tool_names: frozenset = field(default_factory=frozenset)


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
        tool_names=frozenset({}),
    ),
}
