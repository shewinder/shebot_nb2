"""全局预设人格命令（超管）"""
from hoshino import Bot, Event
from hoshino.permission import SUPERUSER

from ..persona import persona_manager
from ..service import sv

add_preset_cmd = sv.on_command('预设人格', aliases=('添加预设人格', '全局预设人格'), permission=SUPERUSER, only_group=False)


@add_preset_cmd.handle()
async def add_global_preset(bot: Bot, event: Event):
    args = str(event.message).strip().split(maxsplit=2)
    if len(args) < 3:
        await add_preset_cmd.finish("请提供人格名称和描述，例如：\n预设人格 猫娘 你是一个可爱的猫娘，说话温柔，喜欢撒娇\n\n或查看已有预设：预设人格列表")
        return

    name = args[1].strip()
    persona_text = args[2].strip()

    if not persona_text:
        await add_preset_cmd.finish("人格描述不能为空")
        return

    success, msg = persona_manager.add_global_preset(name, persona_text)
    await add_preset_cmd.finish(msg)


delete_preset_cmd = sv.on_command('删除预设人格', aliases=('移除预设人格', '删除全局预设'), permission=SUPERUSER, only_group=False)


@delete_preset_cmd.handle()
async def delete_global_preset(bot: Bot, event: Event):
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await delete_preset_cmd.finish("请提供预设人格名称，例如：删除预设人格 猫娘\n使用「预设人格列表」查看所有预设")
        return

    name = args[1].strip()

    success, msg = persona_manager.delete_global_preset(name)
    await delete_preset_cmd.finish(msg)


list_presets_cmd = sv.on_command('预设人格列表', aliases=('全局预设列表', '可用预设人格', '预设列表'), only_group=False)


@list_presets_cmd.handle()
async def list_global_presets(bot: Bot, event: Event):
    presets = persona_manager.get_global_presets()

    if not presets:
        await list_presets_cmd.finish("暂无全局预设人格。\n超级用户可使用「预设人格 名称 描述」来添加预设人格。")
        return

    lines = [f"全局预设人格列表（共 {len(presets)} 个）："]
    for i, (name, persona) in enumerate(presets.items(), 1):
        # 截断过长的描述
        preview = persona[:50] + "..." if len(persona) > 50 else persona
        lines.append(f"{i}. {name}: {preview}")

    lines.append("\n使用「使用人格 名称」或「切换人格 名称」来应用预设人格")
    await list_presets_cmd.finish("\n".join(lines))
