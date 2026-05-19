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
    description="""激活一个 SKILL 以获得其专业能力指导。

当用户请求的功能对应某个可用 SKILL 时调用。激活后其指导内容会在当前会话中持续有效。每个会话最多激活 5 个 SKILL。
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
    
    try:
        # 激活 SKILL（Session 内部处理存在性、重复激活、上限检查）
        success, message, content = session.activate_skill(skill_name)
        
        if success:
            result_lines = [
                f"✅ {message}",
                f"",
                f"📖 描述：{skill.metadata.description}"
            ]
            
            # 添加完整的指导内容，让 AI 在当前轮次就能看到
            if content:
                result_lines.extend([
                    f"",
                    f"=" * 40,
                    f"【{skill_name} 指导内容】",
                    f"=" * 40,
                    f"",
                    content,
                    f"",
                    f"=" * 40,
                    f"【指导内容结束】",
                    f"=" * 40,
                ])
            
            return ok(
                "\n".join(result_lines),
                metadata={
                    "skill_name": skill_name,
                    "already_active": "已经激活" in message,
                    "description": skill.metadata.description,
                    "active_skills_count": len(session.get_active_skills())
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
