"""
SKILL 系统元工具
提供给 AI 使用的 SKILL 发现和激活功能
"""
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from loguru import logger

from ..registry import tool_registry, ok, fail
from ...skills import skill_manager

if TYPE_CHECKING:
    from hoshino import Bot, Event
    from ...session import Session


@tool_registry.register(
    name="activate_skill",
    description="""激活指定的 SKILL，将其指导内容注入到当前对话上下文中。

当用户需要某个 SKILL 的功能，或 AI 判断当前任务需要某个 SKILL 的能力时，调用此工具。

## 参数说明
- skill_name: 要激活的 SKILL 名称（如 "calculate"、"weather" 等）

## 使用场景
1. 用户明确说"帮我计算..." -> 激活 calculate SKILL
2. 用户说"分析这个目录的代码" -> 激活 code-analyzer SKILL
3. 用户发送"#使用 xxx"命令后，AI 自动识别并激活

## 激活流程
1. 检查 SKILL 是否存在
2. 检查是否允许 AI 自动触发（disable_model_invocation=false）
3. 将 SKILL 标记为激活状态
4. 将 SKILL.md 的内容注入到对话上下文

## 注意事项
- 已激活的 SKILL 在当前会话中持续有效
- 单个会话最多激活 5 个 SKILL（防止上下文膨胀）
- 如果 SKILL 禁止 AI 自动触发（disable_model_invocation=true），会返回错误
- 激活后，AI 可以在回复中引用 SKILL 的指导内容

## 示例
activate_skill(skill_name="calculate")
""",
    parameters={
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "要激活的 SKILL 名称"
            }
        },
        "required": ["skill_name"]
    }
)
async def activate_skill(
    skill_name: str,
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    """激活指定 SKILL
    
    Args:
        skill_name: SKILL 名称
        session: 当前会话（自动注入）
        
    Returns:
        激活结果
    """
    from ...config import Config
    conf = Config.get_instance('aichat')
    
    if not conf.enable_skills:
        return fail(
            "SKILL 系统未启用",
            error="SKILL system disabled"
        )
    
    if not session:
        return fail(
            "无法获取当前会话信息",
            error="Missing session context"
        )
    
    skill_name = skill_name.strip()
    if not skill_name:
        return fail(
            "请提供 SKILL 名称",
            error="Missing skill_name"
        )
    
    # 检查 SKILL 是否存在
    skill = skill_manager.get_skill(skill_name)
    if not skill:
        # 尝试查找相似名称
        all_skills = skill_manager.list_skills()
        similar = [s.metadata.name for s in all_skills 
                   if skill_name.lower() in s.metadata.name.lower()]
        
        if similar:
            return fail(
                f"SKILL '{skill_name}' 不存在。您是否想找：{', '.join(similar)}？",
                error=f"Skill not found, similar: {similar}"
            )
        else:
            return fail(
                f"SKILL '{skill_name}' 不存在。查看系统提示中的【SKILL 系统】列表获取可用 SKILL。",
                error="Skill not found"
            )
    
    # 检查是否允许 AI 自动触发
    if skill.metadata.disable_model_invocation:
        return fail(
            f"SKILL '{skill_name}' 禁止 AI 自动触发，请让用户使用「#使用 {skill_name}」命令手动激活",
            error="Model invocation disabled for this skill"
        )
    
    # 检查是否已激活
    if skill_manager.is_skill_active(session.session_id, skill_name):
        return ok(
            f"SKILL '{skill_name}' 已经激活\n\n描述：{skill.metadata.description}",
            metadata={
                "skill_name": skill_name,
                "already_active": True,
                "description": skill.metadata.description,
                "allowed_tools": skill.metadata.allowed_tools
            }
        )
    
    # 检查是否超过最大数量
    active_count = len(skill_manager.get_active_skill_names(session.session_id))
    if active_count >= conf.skill_max_per_session:
        return fail(
            f"当前会话已激活 {active_count} 个 SKILL，达到上限（{conf.skill_max_per_session}）。"
            f"请先使用「#停用技能」释放空间。",
            error="Max skills reached"
        )
    
    try:
        # 激活 SKILL
        success, message, content = skill_manager.activate_skill(
            session.session_id, 
            skill_name
        )
        
        if success:
            # 同时更新 session
            session.activate_skill(skill_name)
            
            result_lines = [
                f"✅ {message}",
                f"",
                f"📖 描述：{skill.metadata.description}"
            ]
            
            if skill.metadata.allowed_tools:
                result_lines.append(f"🔧 可用工具：{', '.join(skill.metadata.allowed_tools)}")
            
            # 添加指导内容预览（前 200 字符）
            if content:
                preview = content[:200].replace('\n', ' ')
                if len(content) > 200:
                    preview += "..."
                result_lines.append(f"\n📋 指导内容预览：{preview}")
            
            return ok(
                "\n".join(result_lines),
                metadata={
                    "skill_name": skill_name,
                    "already_active": False,
                    "description": skill.metadata.description,
                    "allowed_tools": skill.metadata.allowed_tools,
                    "active_skills_count": active_count + 1
                }
            )
        else:
            return fail(
                f"激活 SKILL 失败：{message}",
                error=message
            )
            
    except Exception as e:
        logger.exception(f"activate_skill 执行失败: {e}")
        return fail(f"激活 SKILL 失败: {str(e)}", error=str(e))
