"""
Author: SheBot
Date: 2026-03-31
Description: Skill 管理命令处理器
"""
from hoshino import Bot, Event, Service
from hoshino.permission import SUPERUSER
from hoshino.typing import T_State
from loguru import logger

from . import skill_manager
from .clawhub import clawhub_client
from .installer import get_installer


# 获取服务实例（在 __init__.py 中定义）
def get_sv():
    from .. import sv
    return sv


# ========== 安装命令 ==========

async def install_skill_handler(bot: Bot, event: Event):
    """安装 skill 命令处理器"""
    sv = get_sv()
    
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await bot.send(event, """请提供 skill 来源，例如：
• #安装技能 clawhub:skill-name
• #安装技能 https://example.com/skill.zip
• #安装技能 ./local/path/to/skill""")
        return
    
    source = args[1].strip()
    
    await bot.send(event, f"正在安装 skill: {source}...")
    
    try:
        installer = get_installer(skill_manager.user_paths)
        result = await installer.install(source)
        
        if result.success:
            # 重新加载 skill
            skill_manager.reload()
            
            msg = f"✅ Skill '{result.skill_name}' 安装成功！"
            if result.version:
                msg += f"\n📌 版本: {result.version}"
            msg += "\n\n使用「#技能列表」查看所有可用 skill"
            msg += f"\n使用「#使用 {result.skill_name}」激活 skill"
            
            await bot.send(event, msg)
        else:
            msg = f"❌ 安装失败: {result.message}"
            # 提示可能的解决方案
            if "404" in result.message or "failed" in result.message.lower():
                msg += "\n\n💡 你可以尝试："
                msg += "\n• 检查 skill 名称是否正确 (格式: user/skill-name)"
                msg += "\n• 使用 URL 安装：#安装技能 https://.../skill.zip"
                msg += "\n• 从本地路径安装：#安装技能 ./path/to/skill"
            await bot.send(event, msg)
            
    except Exception as e:
        logger.exception(f"安装 skill 失败: {e}")
        await bot.send(event, f"❌ 安装失败: {e}")


# ========== 搜索命令 ==========

async def search_skill_handler(bot: Bot, event: Event):
    """搜索 skill 命令处理器"""
    sv = get_sv()
    
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await bot.send(event, "请提供搜索关键词，例如：#搜索技能 weather")
        return
    
    query = args[1].strip()
    
    await bot.send(event, f"正在搜索: {query}...")
    
    try:
        results = await clawhub_client.search_skills(query, limit=10)
        
        if not results:
            await bot.send(event, f"未找到与 '{query}' 相关的 skill")
            return
        
        lines = [f"🔍 搜索结果（{len(results)} 个）：\n"]
        
        for i, skill in enumerate(results, 1):
            display_name = skill.name or skill.slug
            lines.append(f"{i}. {display_name}")
            if skill.description:
                lines.append(f"   📖 {skill.description[:60]}...")
            # CLI 返回的相关度分数
            if hasattr(skill, 'score') and skill.score:
                lines.append(f"   🎯 匹配度: {skill.score:.3f}")
            lines.append("")
        
        lines.append("安装命令：")
        best_slug = results[0].slug
        lines.append(f"#安装技能 {best_slug}")
        
        await bot.send(event, "\n".join(lines))
        
    except Exception as e:
        logger.exception(f"搜索 skill 失败: {e}")
        await bot.send(event, f"❌ 搜索失败: {e}")


# ========== 删除命令 ==========

async def delete_skill_handler(bot: Bot, event: Event):
    """删除 skill 命令处理器"""
    sv = get_sv()
    
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await bot.send(event, "请提供要删除的 skill 名称，例如：#删除技能 skill-name")
        return
    
    skill_name = args[1].strip()
    
    # 确认 skill 存在
    skill = skill_manager.get_skill(skill_name)
    if not skill:
        # 检查是否已安装但未启用
        installed = skill_manager.list_installed_skills()
        found = False
        for s, _ in installed:
            if s.metadata.name == skill_name:
                found = True
                skill = s
                break
        
        if not found:
            await bot.send(event, f"SKILL '{skill_name}' 不存在\n使用「#已安装技能」查看所有已安装的 skill")
            return
    
    success, msg = skill_manager.delete_skill(skill_name)
    
    if success:
        await bot.send(event, f"✅ {msg}\n\n该 skill 已完全删除，无法恢复。")
    else:
        await bot.send(event, f"❌ {msg}")


# ========== 禁用命令 ==========

async def disable_skill_handler(bot: Bot, event: Event):
    """禁用 skill 命令处理器"""
    sv = get_sv()
    
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await bot.send(event, "请提供要禁用的 skill 名称，例如：#禁用技能 skill-name")
        return
    
    skill_name = args[1].strip()
    
    success, msg = skill_manager.disable_skill(skill_name)
    
    if success:
        await bot.send(event, f"✅ {msg}\n\n该 skill 将不再被加载，但文件仍保留在本地。\n使用「#启用技能 {skill_name}」可以重新启用。")
    else:
        await bot.send(event, f"❌ {msg}")


# ========== 启用命令 ==========

async def enable_skill_handler(bot: Bot, event: Event):
    """启用 skill 命令处理器"""
    sv = get_sv()
    
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await bot.send(event, "请提供要启用的 skill 名称，例如：#启用技能 skill-name")
        return
    
    skill_name = args[1].strip()
    
    success, msg = skill_manager.enable_skill(skill_name)
    
    if success:
        await bot.send(event, f"✅ {msg}\n\n该 skill 现在可以被使用了。\n使用「#使用 {skill_name}」激活 skill。")
    else:
        await bot.send(event, f"❌ {msg}")


# ========== 更新命令 ==========

async def update_skill_handler(bot: Bot, event: Event):
    """更新 skill 命令处理器"""
    sv = get_sv()
    
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await bot.send(event, "请提供要更新的 skill 名称，例如：#更新技能 skill-name")
        return
    
    skill_name = args[1].strip()
    
    # 检查 skill 是否存在
    installed = skill_manager.list_installed_skills()
    target_skill = None
    target_path = None
    
    for skill, path in installed:
        if skill.metadata.name == skill_name or path.name == skill_name:
            target_skill = skill
            target_path = path
            break
    
    if not target_skill:
        await bot.send(event, f"SKILL '{skill_name}' 未安装\n使用「#已安装技能」查看已安装的 skill")
        return
    
    # 获取 slug (从 _meta.json 或目录名)
    slug = skill_name
    meta_path = target_path / "_meta.json"
    if meta_path.exists():
        try:
            import json
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            slug = meta.get('slug', skill_name)
        except:
            pass
    
    await bot.send(event, f"正在更新 '{skill_name}' (slug: {slug})...")
    
    try:
        from .installer import get_installer
        installer = get_installer(skill_manager.user_paths)
        
        # 使用 clawhub 更新
        success, msg = await clawhub_client.update_skill(slug, target_path)
        
        if success:
            # 重新加载 skill
            skill_manager.reload()
            await bot.send(event, f"✅ '{skill_name}' 更新成功！\n\n使用「#技能列表」查看最新版本")
        else:
            await bot.send(event, f"❌ 更新失败: {msg}")
            
    except Exception as e:
        logger.exception(f"更新 skill 失败: {e}")
        await bot.send(event, f"❌ 更新失败: {e}")


# ========== 已安装列表命令 ==========

async def list_installed_handler(bot: Bot, event: Event):
    """列出已安装 skill 命令处理器"""
    sv = get_sv()
    
    installed = skill_manager.list_installed_skills()
    
    if not installed:
        await bot.send(event, """📦 暂无已安装的 skill

安装 skill：
• #安装技能 clawhub:skill-name
• #搜索技能 <关键词> 查找可用 skill""")
        return
    
    lines = [f"📦 已安装 skill（共 {len(installed)} 个）：\n"]
    
    # 分离已启用和已禁用
    enabled_skills = []
    disabled_skills = []
    
    for skill, path in installed:
        if skill.metadata.enabled:
            enabled_skills.append((skill, path))
        else:
            disabled_skills.append((skill, path))
    
    if enabled_skills:
        lines.append("🟢 已启用：")
        for skill, path in enabled_skills:
            lines.append(f"  • {skill.metadata.name}")
            lines.append(f"    📖 {skill.metadata.description}")
            if skill.metadata.version:
                lines.append(f"    📌 v{skill.metadata.version}")
            lines.append(f"    📂 {path}")
        lines.append("")
    
    if disabled_skills:
        lines.append("⚪ 已禁用：")
        for skill, path in disabled_skills:
            lines.append(f"  • {skill.metadata.name}")
            lines.append(f"    📖 {skill.metadata.description}")
        lines.append("")
    
    lines.append("管理命令：")
    lines.append("• #禁用技能 <名称> - 禁用 skill")
    lines.append("• #启用技能 <名称> - 启用 skill")
    lines.append("• #删除技能 <名称> - 删除 skill")
    
    await bot.send(event, "\n".join(lines))


# ========== ClawHub 测试命令 ==========

async def test_clawhub_handler(bot: Bot, event: Event):
    """测试 ClawHub 连接"""
    await bot.send(event, "正在测试 ClawHub API 连接...")
    
    try:
        # 直接尝试搜索测试
        skills = await clawhub_client.search_skills("test", limit=3)
        if skills:
            msg = "✅ ClawHub 连接正常\n\n📋 示例 skills:\n"
            for skill in skills:
                msg += f"  • {skill.name} ({skill.slug})\n"
                if hasattr(skill, 'score') and skill.score:
                    msg += f"    🎯 匹配度: {skill.score:.3f}\n"
        else:
            msg = "⚠️ 搜索无结果，请检查 CLI 是否已安装: npm install -g clawhub"
        await bot.send(event, msg)
            
    except Exception as e:
        await bot.send(event, f"❌ 测试失败: {e}")


# ========== 命令注册函数 ==========

def register_skill_admin_commands(sv: Service):
    """注册 skill 管理命令"""
    
    # 安装技能
    install_cmd = sv.on_command(
        '#安装技能',
        aliases=('安装skill', '安装技能', 'skill安装'),
        permission=SUPERUSER,
        only_group=False
    )
    install_cmd.handle()(install_skill_handler)
    
    # 搜索技能
    search_cmd = sv.on_command(
        '#搜索技能',
        aliases=('搜索skill', '查找技能', '查找skill', 'skill搜索'),
        only_group=False
    )
    search_cmd.handle()(search_skill_handler)
    
    # 删除技能
    delete_cmd = sv.on_command(
        '#删除技能',
        aliases=('删除skill', '卸载技能', '卸载skill', 'skill删除'),
        permission=SUPERUSER,
        only_group=False
    )
    delete_cmd.handle()(delete_skill_handler)
    
    # 更新技能
    update_cmd = sv.on_command(
        '#更新技能',
        aliases=('更新skill', '升级技能', '升级skill'),
        permission=SUPERUSER,
        only_group=False
    )
    update_cmd.handle()(update_skill_handler)
    
    # 禁用技能
    disable_cmd = sv.on_command(
        '#禁用技能',
        aliases=('禁用skill', '关闭技能', '关闭skill'),
        permission=SUPERUSER,
        only_group=False
    )
    disable_cmd.handle()(disable_skill_handler)
    
    # 启用技能
    enable_cmd = sv.on_command(
        '#启用技能',
        aliases=('启用skill', '打开技能', '打开skill'),
        permission=SUPERUSER,
        only_group=False
    )
    enable_cmd.handle()(enable_skill_handler)
    
    # 已安装技能列表
    list_cmd = sv.on_command(
        '#已安装技能',
        aliases=('已安装skill', '本地技能列表', 'skill列表'),
        only_group=False
    )
    list_cmd.handle()(list_installed_handler)
    
    # ClawHub 测试
    test_cmd = sv.on_command(
        '#测试ClawHub',
        aliases=('clawhub测试', '测试clawhub'),
        permission=SUPERUSER,
        only_group=False
    )
    test_cmd.handle()(test_clawhub_handler)
    
    logger.info("Skill 管理命令已注册")
