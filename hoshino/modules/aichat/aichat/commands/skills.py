"""SKILL 系统命令"""
from hoshino import Bot, Event

from ..config import Config
from ..service import sv
from ..session import session_manager
from ..skills import skill_manager

conf = Config.get_instance('aichat')

list_skills_cmd = sv.on_command('#技能列表', aliases=('列出技能', '可用技能', '技能列表'), only_group=False)


@list_skills_cmd.handle()
async def list_skills(bot: Bot, event: Event):
    """列出所有可用 SKILL"""
    if not conf.enable_skills:
        await list_skills_cmd.finish("SKILL 系统未启用")
        return

    skills = skill_manager.list_skills()

    if not skills:
        await list_skills_cmd.finish("暂无可用 SKILL\n\nSKILL 应放置在以下路径：\n" + "\n".join(conf.skill_search_paths))
        return

    lines = [f"📚 可用 SKILL 列表（共 {len(skills)} 个）：\n"]

    for skill in skills:
        lines.append(f"• {skill.metadata.name}")
        lines.append(f"  📖 {skill.metadata.description}")
        lines.append("")

    lines.append("使用方法：")
    lines.append("• 手动激活：#使用 <skill名称>")
    lines.append("• AI 会根据需要自动激活合适的 SKILL")

    await list_skills_cmd.finish("\n".join(lines))


current_skills_cmd = sv.on_command('#当前技能', aliases=('当前技能', '已激活技能'), only_group=False)


@current_skills_cmd.handle()
async def current_skills(bot: Bot, event: Event):
    """查看当前已激活的 SKILL"""
    if not conf.enable_skills:
        await current_skills_cmd.finish("SKILL 系统未启用")
        return

    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    session = session_manager.get_session(user_id, group_id)
    if not session:
        await current_skills_cmd.finish("当前没有激活的 SKILL\n\n使用「#技能列表」查看可用 SKILL")
        return

    active_skills = session.get_active_skills()

    if not active_skills:
        await current_skills_cmd.finish("当前没有激活的 SKILL\n\n使用「#技能列表」查看可用 SKILL")
        return

    lines = [f"当前已激活 {len(active_skills)} 个 SKILL：\n"]

    for skill_name in active_skills:
        skill = skill_manager.get_skill(skill_name)
        if skill:
            lines.append(f"• {skill.metadata.name}: {skill.metadata.description}")

    await current_skills_cmd.finish("\n".join(lines))
