"""人格管理命令（用户/群默认/全局默认人格）"""
from hoshino import Bot, Event
from hoshino.permission import ADMIN, SUPERUSER

from ..persona import persona_manager
from ..service import sv
from ..session import session_manager

set_persona_cmd = sv.on_command('设置人格', aliases=('设置AI人格',), only_group=False)


@set_persona_cmd.handle()
async def set_persona(bot: Bot, event: Event):
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await set_persona_cmd.finish("请提供人格描述，例如：设置人格 你是一个友好的助手")
        return

    persona_text = args[1].strip()
    if not persona_text:
        await set_persona_cmd.finish("人格描述不能为空")
        return

    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    persona_manager.set_user_persona(user_id, group_id, persona_text)

    session_manager.clear_session(user_id, group_id)

    await set_persona_cmd.finish(f"人格设置成功！\n当前人格：{persona_text}")


set_group_persona_cmd = sv.on_command('设置群默认人格', aliases=('设置群组默认人格',), permission=ADMIN, only_group=True)


@set_group_persona_cmd.handle()
async def set_group_persona(bot: Bot, event: Event):
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await set_group_persona_cmd.finish("请提供人格描述或已保存的人格名称，例如：\n设置群默认人格 你是一个友好的助手\n设置群默认人格 猫娘（使用已保存的人格）")
        return

    input_text = args[1].strip()
    if not input_text:
        await set_group_persona_cmd.finish("人格描述不能为空")
        return

    user_id = event.user_id
    group_id = event.group_id

    saved_persona = persona_manager.find_persona_by_name(user_id, group_id, input_text)

    if saved_persona:
        persona_text = saved_persona
        persona_manager.set_group_default_persona(group_id, persona_text)
        await set_group_persona_cmd.finish(f"群组默认人格设置成功！\n使用已保存的人格：{input_text}\n人格内容：{persona_text[:100]}{'...' if len(persona_text) > 100 else ''}")
    else:
        persona_text = input_text
        persona_manager.set_group_default_persona(group_id, persona_text)
        await set_group_persona_cmd.finish(f"群组默认人格设置成功！\n当前人格：{persona_text}")


set_global_persona_cmd = sv.on_command('设置全局默认人格', aliases=('设置全局人格',), permission=SUPERUSER, only_group=False)


@set_global_persona_cmd.handle()
async def set_global_persona(bot: Bot, event: Event):
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await set_global_persona_cmd.finish("请提供人格描述或已保存的人格名称，例如：\n设置全局默认人格 你是一个友好的助手\n设置全局默认人格 猫娘（使用已保存的人格）")
        return

    input_text = args[1].strip()
    if not input_text:
        await set_global_persona_cmd.finish("人格描述不能为空")
        return

    user_id = event.user_id

    saved_persona = persona_manager.find_persona_by_name(user_id, None, input_text)

    if saved_persona:
        persona_text = saved_persona
        persona_manager.set_global_default_persona(persona_text)
        await set_global_persona_cmd.finish(f"全局默认人格设置成功！\n使用已保存的人格：{input_text}\n人格内容：{persona_text[:100]}{'...' if len(persona_text) > 100 else ''}")
    else:
        persona_text = input_text
        persona_manager.set_global_default_persona(persona_text)
        await set_global_persona_cmd.finish(f"全局默认人格设置成功！\n当前人格：{persona_text}")


view_persona_cmd = sv.on_command('查看人格', aliases=('查看AI人格', '当前人格'), only_group=False)


@view_persona_cmd.handle()
async def view_persona(bot: Bot, event: Event):
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    effective_persona = persona_manager.get_persona(user_id, group_id)

    if effective_persona:
        await view_persona_cmd.finish(f"当前生效的人格：\n{effective_persona}")
    else:
        await view_persona_cmd.finish("未设置人格，使用默认行为")


clear_persona_cmd = sv.on_command('清除人格', aliases=('清除AI人格',), only_group=False)


@clear_persona_cmd.handle()
async def clear_persona(bot: Bot, event: Event):
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    if persona_manager.clear_user_persona(user_id, group_id):
        session_manager.clear_session(user_id, group_id)
        await clear_persona_cmd.finish("人格已清除，将使用默认人格")
    else:
        await clear_persona_cmd.finish("未设置用户人格，无需清除")


save_persona_cmd = sv.on_command('保存人格', aliases=('保存AI人格',), only_group=False)


@save_persona_cmd.handle()
async def save_persona(bot: Bot, event: Event):
    args = str(event.message).strip().split(maxsplit=2)
    if len(args) < 3:
        await save_persona_cmd.finish("请提供人格名称和描述，例如：保存人格 猫娘 你是一个可爱的猫娘")
        return

    name = args[1].strip()
    persona_text = args[2].strip()

    if not persona_text:
        await save_persona_cmd.finish("人格描述不能为空")
        return

    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    success, msg = persona_manager.save_persona(user_id, group_id, name, persona_text)
    await save_persona_cmd.finish(msg)


list_personas_cmd = sv.on_command('列出人格', aliases=('查看保存的人格', '已保存人格', '人格列表'), only_group=False)


@list_personas_cmd.handle()
async def list_personas(bot: Bot, event: Event):
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    saved_personas = persona_manager.get_saved_personas(user_id, group_id)
    global_presets = persona_manager.get_global_presets()

    lines = []

    if saved_personas:
        lines.append(f"📁 已保存的人格（{len(saved_personas)} 个）：")
        for i, (name, persona) in enumerate(saved_personas.items(), 1):
            # 截断过长的描述
            preview = persona[:50] + "..." if len(persona) > 50 else persona
            lines.append(f"  {i}. {name}: {preview}")
    else:
        lines.append("📁 已保存的人格（0 个）：无")
        lines.append("  使用「保存人格 名称 描述」或「导入角色卡」来添加")

    if global_presets:
        lines.append(f"\n🌐 全局预设人格（{len(global_presets)} 个）：")
        for i, (name, persona) in enumerate(global_presets.items(), 1):
            # 截断过长的描述
            preview = persona[:50] + "..." if len(persona) > 50 else persona
            lines.append(f"  {i}. {name}: {preview}")

    lines.append(f"\n使用「使用人格 名称」来快捷设置人格")
    await list_personas_cmd.finish("\n".join(lines))


use_persona_cmd = sv.on_command('使用人格', aliases=('切换人格', '应用人格'), only_group=False)


@use_persona_cmd.handle()
async def use_persona(bot: Bot, event: Event):
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await use_persona_cmd.finish("请提供人格名称，例如：使用人格 猫娘\n使用「列出人格」查看自己的保存人格，「预设人格列表」查看全局预设人格")
        return

    name = args[1].strip()

    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    persona_text = persona_manager.find_persona_by_name(user_id, group_id, name)

    if not persona_text:
        msg = f"未找到名为 '{name}' 的人格。\n"
        msg += "使用「列出人格」查看自己保存的人格\n"
        msg += "使用「预设人格列表」查看可用的全局预设人格"
        await use_persona_cmd.finish(msg)
        return

    persona_manager.set_user_persona(user_id, group_id, persona_text)
    session_manager.clear_session(user_id, group_id)

    user_saved = persona_manager.get_saved_persona(user_id, group_id, name)
    if user_saved:
        source = "[个人保存]"
    else:
        source = "[全局预设]"

    await use_persona_cmd.finish(f"已切换到人格 '{name}' {source}\n人格内容：{persona_text[:100]}{'...' if len(persona_text) > 100 else ''}")


delete_persona_cmd = sv.on_command('删除人格', aliases=('移除人格', '删除保存的人格'), only_group=False)


@delete_persona_cmd.handle()
async def delete_persona(bot: Bot, event: Event):
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await delete_persona_cmd.finish("请提供人格名称，例如：删除人格 猫娘\n使用「列出人格」查看已保存的人格")
        return

    name = args[1].strip()

    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)

    success, msg = persona_manager.delete_saved_persona(user_id, group_id, name)
    await delete_persona_cmd.finish(msg)
