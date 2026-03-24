"""
AI Chat插件
支持以#开头的消息触发AI对话，支持session管理、人格管理和多模态
"""
from typing import Tuple
from loguru import logger
from hoshino import Bot, Event, Service
from hoshino.permission import ADMIN, SUPERUSER

from .api import api_manager
from .chat import call_ai_api, download_image_to_base64, handle_ai_chat
from .character_import import parse_character_png
from .config import Config
from .persona import persona_manager
from .session import Session, SessionManager, session_manager
from hoshino.util import aiohttpx, get_event_imageurl
from hoshino.util.message_util import extract_images_from_reply

# 加载配置
conf = Config.get_instance('aichat')

# 创建Service
sv = Service('aichat', help_='''AI聊天插件
基础用法：
  #消息   以#开头触发AI对话
  进入对话模式 [--option 指导标准]  进入免#触发模式，加--option同时开启选项模式
  退出对话模式/结束对话模式  退出连续对话模式
  查看对话模式  查看当前模式状态
选项模式：
  开启选项模式 [指导标准]  开启选项生成，如：开启选项模式 暧昧场景程度
  关闭选项模式  关闭选项生成
  选项状态  查看选项模式状态
对话管理：
  清除对话/清空对话/重置对话  清除当前对话历史
  回溯/回退 [N]  回溯N条对话
人格设置：
  设置人格 [描述]  设置当前人格
  使用人格 [名称]  使用已保存的人格
  保存人格 [名称] [描述]  保存人格
  列出人格  查看已保存的人格
  查看人格  查看当前生效的人格
  清除人格  清除用户人格设置
API/模型管理：
  当前模型  查看当前API厂商和模型
  切换API [厂商名]  切换API厂商，无参数时列出可用厂商（超管）
  切换模型 [模型名/序号]  切换模型，无参数时列出可用模型（超管）
工具功能（需要模型支持 Tool Calling）：
  支持画图、搜索等工具调用
  注意：在 config 中设置 supports_tools=true 启用
角色卡：
  导入角色卡 [图片]  从PNG角色卡导入人格
  导入全局角色卡 [图片]  导入全局预设人格（超管）
预设人格（超管）：
  预设人格 [名称] [描述]  添加/更新预设人格
  预设人格列表  列出全局预设人格
  删除预设人格 [名称]  删除预设人格''')

# ========== 注册消息处理器 ==========
sv.on_message(priority=10, block=False, only_group=False).handle()(handle_ai_chat)

# ========== 进入连续对话模式命令 ==========
enter_chat_mode_cmd = sv.on_command('进入对话模式', aliases=('连续对话', '免井号对话', '聊天模式', '进入聊天'), only_group=False, block=True)

@enter_chat_mode_cmd.handle()
async def enter_chat_mode(bot: Bot, event: Event):
    """进入连续对话模式，无需#前缀即可触发AI对话。支持 --option 参数同时开启选项模式"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    # 解析参数，检查是否有 --option
    full_msg = str(event.message).strip()
    choice_mode_enabled = False
    choice_guideline = None
    
    # 检查是否包含 --option 参数
    if '--option' in full_msg:
        choice_mode_enabled = True
        # 提取 --option 后面的内容作为指导标准
        option_idx = full_msg.find('--option')
        after_option = full_msg[option_idx + len('--option'):].strip()
        if after_option:
            choice_guideline = after_option
    
    # 设置连续对话模式
    session_manager.set_continuous_mode(user_id, group_id, True)
    
    # 如果开启了选项模式，同时设置选项模式
    if choice_mode_enabled:
        session_manager.set_choice_mode(user_id, group_id, True, choice_guideline)
    
    # 获取或创建session（确保人格设置正确）
    persona = persona_manager.get_persona(user_id, group_id)
    session = session_manager.get_session(user_id, group_id, persona)
    
    msg = "已进入连续对话模式！\n现在可以直接发送消息，无需 # 前缀即可与AI对话。\n"
    msg += f"当前人格：{persona[:30]}..." if persona else "当前人格：默认"
    
    if choice_mode_enabled:
        msg += "\n\n✅ 已同时开启选项生成模式！"
        if choice_guideline:
            msg += f"\n📋 指导标准：{choice_guideline}"
        msg += "\nAI回复时会自动生成3个选项供你选择，发送 1/2/3 即可快速选择。"
    
    msg += "\n\n提示：\n- 发送「退出对话模式」退出此模式\n- 发送「清除对话」清空当前对话历史\n- session过期后将自动退出此模式"
    
    await enter_chat_mode_cmd.finish(msg)

# ========== 退出连续对话模式命令 ==========
exit_chat_mode_cmd = sv.on_command('退出对话模式', aliases=('退出聊天', '结束对话模式'), only_group=False)

@exit_chat_mode_cmd.handle()
async def exit_chat_mode(bot: Bot, event: Event):
    """退出连续对话模式"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    was_in_mode = session_manager.is_continuous_mode(user_id, group_id)
    
    if not was_in_mode:
        await exit_chat_mode_cmd.finish("你当前不在连续对话模式中，发送「进入对话模式」来开启")
        return
    
    # 退出连续对话模式
    session_manager.set_continuous_mode(user_id, group_id, False)
    await exit_chat_mode_cmd.finish("已退出连续对话模式。\n现在需要使用 # 前缀来触发AI对话。")

# ========== 查看当前对话模式命令 ==========
check_chat_mode_cmd = sv.on_command('查看对话模式', aliases=('对话模式状态',), only_group=False)

@check_chat_mode_cmd.handle()
async def check_chat_mode(bot: Bot, event: Event):
    """查看当前是否处于连续对话模式"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    in_mode = session_manager.is_continuous_mode(user_id, group_id)
    
    if in_mode:
        await check_chat_mode_cmd.finish("当前处于「连续对话模式」，直接发送消息即可与AI对话\n发送「退出对话模式」退出此模式")
    else:
        await check_chat_mode_cmd.finish("当前处于「普通模式」，需要使用 # 前缀触发AI对话\n发送「进入对话模式」开启免#触发")

# ========== 开启选项模式命令 ==========
enable_choice_mode_cmd = sv.on_command('开启选项模式', aliases=('打开选项模式', '选项模式开启'), only_group=False, block=True)

@enable_choice_mode_cmd.handle()
async def enable_choice_mode(bot: Bot, event: Event):
    """开启选项生成模式，AI回复时会生成3个选项供用户选择"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    # 检查是否在连续对话模式
    in_continuous_mode = session_manager.is_continuous_mode(user_id, group_id)
    if not in_continuous_mode:
        await enable_choice_mode_cmd.finish("选项模式仅在「连续对话模式」下可用\n请先发送「进入对话模式」开启连续对话")
        return
    
    # 获取指导标准（可选）
    args = str(event.message).strip().split(maxsplit=1)
    guideline = args[1].strip() if len(args) > 1 else None
    
    # 开启选项模式
    session_manager.set_choice_mode(user_id, group_id, True, guideline)
    
    msg = "✅ 已开启选项生成模式！\n"
    if guideline:
        msg += f"📋 指导标准：{guideline}\n"
    msg += "\n现在AI回复时会自动生成3个选项供你选择。\n"
    msg += "发送数字 1/2/3 即可快速选择对应选项。\n\n"
    msg += "提示：\n- 发送「关闭选项模式」关闭此功能\n- 发送「选项状态」查看当前状态"
    
    await enable_choice_mode_cmd.finish(msg)

# ========== 关闭选项模式命令 ==========
disable_choice_mode_cmd = sv.on_command('关闭选项模式', aliases=('退出选项模式', '选项模式关闭'), only_group=False)

@disable_choice_mode_cmd.handle()
async def disable_choice_mode(bot: Bot, event: Event):
    """关闭选项生成模式"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    choice_enabled, _ = session_manager.get_choice_mode(user_id, group_id)
    
    if not choice_enabled:
        await disable_choice_mode_cmd.finish("选项生成模式当前未开启。\n发送「开启选项模式」来开启此功能。")
        return
    
    # 关闭选项模式
    session_manager.set_choice_mode(user_id, group_id, False)
    await disable_choice_mode_cmd.finish("已关闭选项生成模式。\nAI将不再自动生成选项。")

# ========== 查看选项模式状态命令 ==========
check_choice_mode_cmd = sv.on_command('选项状态', aliases=('选项模式状态', '查看选项模式'), only_group=False)

@check_choice_mode_cmd.handle()
async def check_choice_mode(bot: Bot, event: Event):
    """查看当前选项模式状态"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    in_continuous_mode = session_manager.is_continuous_mode(user_id, group_id)
    choice_enabled, guideline = session_manager.get_choice_mode(user_id, group_id)
    
    if not in_continuous_mode:
        await check_choice_mode_cmd.finish("当前不在连续对话模式中。\n发送「进入对话模式」开启连续对话，然后可以「开启选项模式」")
        return
    
    if choice_enabled:
        msg = "当前选项生成模式：🟢 已开启\n"
        if guideline:
            msg += f"📋 指导标准：{guideline}\n"
        msg += "\nAI回复时会自动生成3个选项\n发送 1/2/3 快速选择"
    else:
        msg = "当前选项生成模式：⚪ 已关闭\n"
        msg += "发送「开启选项模式」开启此功能"
    
    await check_choice_mode_cmd.finish(msg)

# ========== 清除session命令 ==========
clear_cmd = sv.on_command('清除对话', aliases=('清空对话', '重置对话'), only_group=False)

@clear_cmd.handle()
async def clear_session(bot: Bot, event: Event):
    """清除当前session"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    if session_manager.clear_session(user_id, group_id):
        await bot.send(event, "对话历史已清除")
    else:
        await bot.send(event, "没有找到对话历史")

# ========== 回溯对话命令 ==========
rollback_cmd = sv.on_command('回溯', aliases=('回退', '删除对话', '返回'), only_group=False, block=True)

@rollback_cmd.handle()
async def rollback_session(bot: Bot, event: Event):
    """回溯对话，删除最近的 N 条对话"""
    args = str(event.message).strip().split()
    
    # 默认回溯1条
    count = 1
    if len(args) >= 2:
        try:
            count = int(args[1].strip())
            if count < 1:
                await rollback_cmd.finish("回溯条数必须大于0，例如：回溯 3")
                return
            if count > 50:
                await rollback_cmd.finish("一次最多回溯50条对话")
                return
        except ValueError:
            await rollback_cmd.finish("请输入有效的数字，例如：回溯 3")
            return
    
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    deleted = session_manager.rollback_messages(user_id, group_id, count)
    
    if deleted == 0:
        await rollback_cmd.finish("没有可回溯的对话记录")
    elif deleted < count * 2:
        # 只删除了部分（消息不够）
        actual_pairs = deleted // 2
        await rollback_cmd.finish(f"已回溯 {actual_pairs} 条对话（共删除 {deleted} 条消息，历史记录不足）")
    else:
        await rollback_cmd.finish(f"已回溯 {count} 条对话（共删除 {deleted} 条消息）")

# ========== 设置用户人格命令 ==========
set_persona_cmd = sv.on_command('设置人格', aliases=('设置AI人格',), only_group=False)

@set_persona_cmd.handle()
async def set_persona(bot: Bot, event: Event):
    """设置用户人格"""
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
    
    # 清除当前session，以便新人格生效
    session_manager.clear_session(user_id, group_id)
    
    await set_persona_cmd.finish(f"人格设置成功！\n当前人格：{persona_text}")

# ========== 设置群组默认人格命令（需要管理员权限） ==========
set_group_persona_cmd = sv.on_command('设置群默认人格', aliases=('设置群组默认人格',), permission=ADMIN, only_group=True)

@set_group_persona_cmd.handle()
async def set_group_persona(bot: Bot, event: Event):
    """设置群组默认人格（支持使用已保存的人格名称）"""
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
    
    # 先尝试查找已保存的人格
    saved_persona = persona_manager.get_saved_persona(user_id, None, input_text)
    
    if saved_persona:
        # 使用已保存的人格
        persona_text = saved_persona
        persona_manager.set_group_default_persona(group_id, persona_text)
        await set_group_persona_cmd.finish(f"群组默认人格设置成功！\n使用已保存的人格：{input_text}\n人格内容：{persona_text[:100]}{'...' if len(persona_text) > 100 else ''}")
    else:
        # 当作人格描述处理
        persona_text = input_text
        persona_manager.set_group_default_persona(group_id, persona_text)
        await set_group_persona_cmd.finish(f"群组默认人格设置成功！\n当前人格：{persona_text}")

# ========== 设置全局默认人格命令（需要超级用户权限） ==========
set_global_persona_cmd = sv.on_command('设置全局默认人格', aliases=('设置全局人格',), permission=SUPERUSER, only_group=False)

@set_global_persona_cmd.handle()
async def set_global_persona(bot: Bot, event: Event):
    """设置全局默认人格（支持使用已保存的人格名称）"""
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await set_global_persona_cmd.finish("请提供人格描述或已保存的人格名称，例如：\n设置全局默认人格 你是一个友好的助手\n设置全局默认人格 猫娘（使用已保存的人格）")
        return
    
    input_text = args[1].strip()
    if not input_text:
        await set_global_persona_cmd.finish("人格描述不能为空")
        return
    
    user_id = event.user_id
    
    # 先尝试查找已保存的人格
    saved_persona = persona_manager.get_saved_persona(user_id, None, input_text)
    
    if saved_persona:
        # 使用已保存的人格
        persona_text = saved_persona
        persona_manager.set_global_default_persona(persona_text)
        await set_global_persona_cmd.finish(f"全局默认人格设置成功！\n使用已保存的人格：{input_text}\n人格内容：{persona_text[:100]}{'...' if len(persona_text) > 100 else ''}")
    else:
        # 当作人格描述处理
        persona_text = input_text
        persona_manager.set_global_default_persona(persona_text)
        await set_global_persona_cmd.finish(f"全局默认人格设置成功！\n当前人格：{persona_text}")

# ========== 查看人格命令 ==========
view_persona_cmd = sv.on_command('查看人格', aliases=('查看AI人格', '当前人格'), only_group=False)

@view_persona_cmd.handle()
async def view_persona(bot: Bot, event: Event):
    """查看当前生效的人格"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    effective_persona = persona_manager.get_persona(user_id, group_id)
    
    if effective_persona:
        await view_persona_cmd.finish(f"当前生效的人格：\n{effective_persona}")
    else:
        await view_persona_cmd.finish("未设置人格，使用默认行为")

# ========== 清除人格命令 ==========
clear_persona_cmd = sv.on_command('清除人格', aliases=('清除AI人格',), only_group=False)

@clear_persona_cmd.handle()
async def clear_persona(bot: Bot, event: Event):
    """清除用户人格设置"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    if persona_manager.clear_user_persona(user_id, group_id):
        # 清除当前session，以便使用默认人格
        session_manager.clear_session(user_id, group_id)
        await clear_persona_cmd.finish("人格已清除，将使用默认人格")
    else:
        await clear_persona_cmd.finish("未设置用户人格，无需清除")

# ========== 保存人格命令 ==========
save_persona_cmd = sv.on_command('保存人格', aliases=('保存AI人格',), only_group=False)

@save_persona_cmd.handle()
async def save_persona(bot: Bot, event: Event):
    """保存人格到用户的人格列表"""
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

# ========== 列出已保存人格命令 ==========
list_personas_cmd = sv.on_command('列出人格', aliases=('查看保存的人格', '已保存人格', '人格列表'), only_group=False)

@list_personas_cmd.handle()
async def list_personas(bot: Bot, event: Event):
    """列出用户保存的所有人格和全局预设人格"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    saved_personas = persona_manager.get_saved_personas(user_id, group_id)
    global_presets = persona_manager.get_global_presets()
    
    lines = []
    
    # 显示用户保存的人格
    if saved_personas:
        lines.append(f"📁 已保存的人格（{len(saved_personas)} 个）：")
        for i, (name, persona) in enumerate(saved_personas.items(), 1):
            # 截断过长的描述
            preview = persona[:50] + "..." if len(persona) > 50 else persona
            lines.append(f"  {i}. {name}: {preview}")
    else:
        lines.append("📁 已保存的人格（0 个）：无")
        lines.append("  使用「保存人格 名称 描述」或「导入角色卡」来添加")
    
    # 显示全局预设人格
    if global_presets:
        lines.append(f"\n🌐 全局预设人格（{len(global_presets)} 个）：")
        for i, (name, persona) in enumerate(global_presets.items(), 1):
            # 截断过长的描述
            preview = persona[:50] + "..." if len(persona) > 50 else persona
            lines.append(f"  {i}. {name}: {preview}")
    
    lines.append(f"\n使用「使用人格 名称」来快捷设置人格")
    await list_personas_cmd.finish("\n".join(lines))

# ========== 使用已保存人格命令（支持用户保存的人格和全局预设人格） ==========
use_persona_cmd = sv.on_command('使用人格', aliases=('切换人格', '应用人格'), only_group=False)

@use_persona_cmd.handle()
async def use_persona(bot: Bot, event: Event):
    """使用已保存的人格（支持用户人格和全局预设人格）"""
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await use_persona_cmd.finish("请提供人格名称，例如：使用人格 猫娘\n使用「列出人格」查看自己的保存人格，「预设人格列表」查看全局预设人格")
        return
    
    name = args[1].strip()
    
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    # 优先查找用户自己保存的人格，然后是全局预设人格
    persona_text = persona_manager.find_persona_by_name(user_id, group_id, name)
    
    if not persona_text:
        msg = f"未找到名为 '{name}' 的人格。\n"
        msg += "使用「列出人格」查看自己保存的人格\n"
        msg += "使用「预设人格列表」查看可用的全局预设人格"
        await use_persona_cmd.finish(msg)
        return
    
    # 设置为当前人格
    persona_manager.set_user_persona(user_id, group_id, persona_text)
    
    # 清除当前session，以便新人格生效
    session_manager.clear_session(user_id, group_id)
    
    # 判断实际应用的来源（先检查个人保存，再检查全局预设）
    user_saved = persona_manager.get_saved_persona(user_id, group_id, name)
    if user_saved:
        source = "[个人保存]"
    else:
        source = "[全局预设]"
    
    await use_persona_cmd.finish(f"已切换到人格 '{name}' {source}\n人格内容：{persona_text[:100]}{'...' if len(persona_text) > 100 else ''}")

# ========== 删除已保存人格命令 ==========
delete_persona_cmd = sv.on_command('删除人格', aliases=('移除人格', '删除保存的人格'), only_group=False)

@delete_persona_cmd.handle()
async def delete_persona(bot: Bot, event: Event):
    """删除已保存的人格"""
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await delete_persona_cmd.finish("请提供人格名称，例如：删除人格 猫娘\n使用「列出人格」查看已保存的人格")
        return
    
    name = args[1].strip()
    
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    success, msg = persona_manager.delete_saved_persona(user_id, group_id, name)
    await delete_persona_cmd.finish(msg)

# ========== 切换API命令（仅超级用户） ==========
switch_api_cmd = sv.on_command('切换API', aliases=('切换厂商', '选择API'), permission=SUPERUSER, only_group=False)

@switch_api_cmd.handle()
async def switch_api(bot: Bot, event: Event):
    """切换当前使用的 API 厂商（仅超级用户）
    
    无参数：列出可用 API 厂商
    有参数：切换到指定 API 厂商（不区分大小写）
    """
    args = str(event.message).strip().split(maxsplit=1)
    apis = conf.get_apis()
    if not apis:
        await switch_api_cmd.finish("未配置任何 API 厂商，请联系管理员在 config/aichat.json 中配置 apis")
        return
    
    current_api = api_manager.get_current_api()
    
    # 无参数：列出可用 API
    if len(args) < 2:
        lines = ["可用 API 厂商："]
        for i, a in enumerate(apis, 1):
            mark = " (当前)" if a.api == current_api else ""
            lines.append(f"{i}. {a.api}{mark} - 模型: {a.model}")
        lines.append("\n请使用「切换API 厂商名」切换")
        await switch_api_cmd.finish("\n".join(lines))
        return
    
    # 有参数：切换 API
    api_input = args[1].strip()
    
    # 尝试精确匹配（不区分大小写）
    target = None
    for a in apis:
        if a.api.lower() == api_input.lower():
            target = a
            break
    
    # 尝试序号匹配
    if target is None:
        try:
            idx = int(api_input) - 1
            if 0 <= idx < len(apis):
                target = apis[idx]
        except ValueError:
            pass
    
    if not target:
        await switch_api_cmd.finish(f"未找到 API 厂商「{api_input}」，请检查名称或使用序号")
        return
    
    api_manager.set_current_api(target.api)
    await switch_api_cmd.finish(f"已切换 API 厂商为：{target.api}\n当前模型：{target.model}")

# ========== 切换模型命令（仅超级用户） ==========
switch_model_cmd = sv.on_command('切换模型', aliases=('选择模型', '设置模型'), permission=SUPERUSER, only_group=False)

@switch_model_cmd.handle()
async def switch_model(bot: Bot, event: Event):
    """切换当前 API 厂商使用的模型（仅超级用户）
    
    无参数：从 API 获取可用模型列表并显示
    有参数：切换到指定模型（支持序号或模型名）
    """
    args = str(event.message).strip().split(maxsplit=1)
    
    current_api = api_manager.get_current_api()
    entry = conf.get_api_by_name(current_api)
    if not entry:
        await switch_model_cmd.finish("当前 API 厂商无效")
        return
    
    # 无参数：获取并显示可用模型列表
    if len(args) < 2:
        await switch_model_cmd.send(f"正在获取 {current_api} 支持的模型列表...")
        try:
            models = await api_manager.get_available_models()
            if not models:
                await switch_model_cmd.finish(f"无法获取 {current_api} 的模型列表，请直接输入模型名称切换\n当前配置模型：{entry.model}")
                return
            
            lines = [f"{current_api} 支持的模型（共 {len(models)} 个）："]
            # 只显示前 20 个，避免消息过长
            display_models = models[:20]
            for i, m in enumerate(display_models, 1):
                mark = " (当前)" if m == entry.model else ""
                lines.append(f"{i}. {m}{mark}")
            if len(models) > 20:
                lines.append(f"... 还有 {len(models) - 20} 个模型")
            lines.append(f"\n请输入「切换模型 序号」或「切换模型 模型名」")
            await switch_model_cmd.finish("\n".join(lines))
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            await switch_model_cmd.finish(f"获取模型列表失败，请直接输入模型名称切换\n当前配置模型：{entry.model}")
        return
    
    # 有参数：切换模型
    model_input = args[1].strip()
    old_model = entry.model
    target_model = None
    
    # 尝试序号匹配
    try:
        idx = int(model_input) - 1
        models = await api_manager.get_available_models()
        if models and 0 <= idx < len(models):
            target_model = models[idx]
    except ValueError:
        pass
    
    # 序号匹配失败，使用输入的模型名
    if target_model is None:
        target_model = model_input
    
    if api_manager.set_current_model(target_model):
        await switch_model_cmd.finish(f"已切换模型：{old_model} → {target_model}\n当前 API 厂商：{current_api}")
    else:
        await switch_model_cmd.finish("切换模型失败")

# ========== 当前模型命令 ==========
current_model_cmd = sv.on_command('当前模型', aliases=('查看模型', '当前大模型'), only_group=False)

@current_model_cmd.handle()
async def current_model(bot: Bot, event: Event):
    """查看当前使用的模型"""
    api_name = api_manager.get_current_api()
    model_name = api_manager.get_current_model()
    await current_model_cmd.finish(f"当前 API 厂商：{api_name}\n当前模型：{model_name}")


# ========== 全局预设人格管理命令（仅超级用户） ==========

# 添加/更新全局预设人格命令
add_preset_cmd = sv.on_command('预设人格', aliases=('添加预设人格', '全局预设人格'), permission=SUPERUSER, only_group=False)

@add_preset_cmd.handle()
async def add_global_preset(bot: Bot, event: Event):
    """添加或更新全局预设人格（仅超级用户）"""
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


# 删除全局预设人格命令
delete_preset_cmd = sv.on_command('删除预设人格', aliases=('移除预设人格', '删除全局预设'), permission=SUPERUSER, only_group=False)

@delete_preset_cmd.handle()
async def delete_global_preset(bot: Bot, event: Event):
    """删除全局预设人格（仅超级用户）"""
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await delete_preset_cmd.finish("请提供预设人格名称，例如：删除预设人格 猫娘\n使用「预设人格列表」查看所有预设")
        return
    
    name = args[1].strip()
    
    success, msg = persona_manager.delete_global_preset(name)
    await delete_preset_cmd.finish(msg)


# 列出全局预设人格命令
list_presets_cmd = sv.on_command('预设人格列表', aliases=('全局预设列表', '可用预设人格', '预设列表'), only_group=False)

@list_presets_cmd.handle()
async def list_global_presets(bot: Bot, event: Event):
    """列出所有全局预设人格"""
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


async def _process_character_images(event: Event, bot: Bot, save_as_global: bool = False) -> Tuple[int, int, int, list, list]:
    """
    处理角色卡图片的通用逻辑
    
    Args:
        event: 事件对象
        bot: Bot 对象
        save_as_global: 是否保存为全局预设人格
        
    Returns:
        (成功数量, 失败数量, 跳过数量, 导入的名称列表, 失败原因列表)
    """
    image_urls = []
    
    # 1. 获取当前消息中的图片
    image_urls.extend(get_event_imageurl(event))
    
    # 2. 获取回复/引用消息中的图片
    try:
        image_urls.extend(await extract_images_from_reply(event, bot))
    except Exception as e:
        logger.debug(f"提取引用消息图片失败: {e}")
    
    if not image_urls:
        return 0, 0, 0, [], ["未找到图片"]
    
    # 处理所有图片
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    success_count = 0
    fail_count = 0
    skip_count = 0
    imported_names = []
    fail_reasons = []
    
    for i, image_url in enumerate(image_urls, 1):
        try:
            # 下载图片
            resp = await aiohttpx.get(image_url)
            if not resp.ok:
                fail_count += 1
                fail_reasons.append(f"第{i}张：下载失败 HTTP {resp.status_code}")
                continue
            
            image_data = resp.content
            if not image_data:
                fail_count += 1
                fail_reasons.append(f"第{i}张：图片数据为空")
                continue
            
            # 尝试解析 PNG 角色卡
            success, char_card, msg = parse_character_png(image_data)
            
            if not success or not char_card:
                # 解析失败，可能是普通图片而非角色卡，跳过
                skip_count += 1
                logger.debug(f"第{i}张图片不是有效的角色卡：{msg}")
                continue
            
            # 转换为角色人格
            persona_name = char_card.name
            persona_text = char_card.to_persona_text()
            
            if save_as_global:
                # 保存为全局预设人格
                success_save, msg_save = persona_manager.add_global_preset(persona_name, persona_text)
            else:
                # 保存为用户的人格
                success_save, msg_save = persona_manager.save_persona(user_id, group_id, persona_name, persona_text)
            
            if success_save:
                success_count += 1
                imported_names.append(persona_name)
            else:
                # 保存失败
                fail_count += 1
                fail_reasons.append(f"{persona_name}：{msg_save}")
                
        except Exception as e:
            logger.exception(f"处理第{i}张图片失败: {e}")
            fail_count += 1
            fail_reasons.append(f"第{i}张：处理异常 {e}")
    
    return success_count, fail_count, skip_count, imported_names, fail_reasons


def _build_import_result_message(
    success_count: int, 
    fail_count: int, 
    skip_count: int, 
    imported_names: list, 
    fail_reasons: list,
    total_images: int,
    is_global: bool = False
) -> str:
    """构建导入结果消息"""
    if success_count == 0 and fail_count == 0 and skip_count > 0:
        return f"未找到有效的角色卡图片。\n共检测 {total_images} 张图片，都不是有效的 TavernAI / SillyTavern PNG 角色卡。"
    
    if success_count == 0:
        msg_lines = [f"❌ 导入失败，共 {fail_count} 个错误："]
        msg_lines.extend(fail_reasons[:5])
        if len(fail_reasons) > 5:
            msg_lines.append(f"...还有 {len(fail_reasons) - 5} 个错误")
        return "\n".join(msg_lines)
    
    # 有成功导入的
    scope = "全局预设" if is_global else "个人"
    msg_lines = [f"✅ 成功导入 {success_count} 个{scope}角色卡"]
    
    if len(imported_names) <= 5:
        msg_lines.append("导入的角色：" + ", ".join(f"「{n}」" for n in imported_names))
    else:
        msg_lines.append(f"导入的角色：{', '.join(f'「{n}」' for n in imported_names[:5])} 等共 {len(imported_names)} 个")
    
    if fail_count > 0:
        msg_lines.append(f"\n⚠️ {fail_count} 个导入失败")
    
    if skip_count > 0:
        msg_lines.append(f"\nℹ️ {skip_count} 张图片不是角色卡，已跳过")
    
    if is_global:
        msg_lines.append(f"\n使用「预设人格列表」查看全局预设")
        msg_lines.append(f"使用「使用人格 <角色名>」来应用角色")
    else:
        msg_lines.append(f"\n使用「列出人格」查看已保存的角色")
        msg_lines.append(f"使用「使用人格 <角色名>」来应用角色")
    
    return "\n".join(msg_lines)


# ========== 导入角色卡命令（个人） ==========
import_persona_cmd = sv.on_command('导入角色卡', aliases=('导入人格', '加载角色卡'), only_group=False)

@import_persona_cmd.handle()
async def import_persona(bot: Bot, event: Event):
    """从 PNG 图片导入角色卡到个人保存列表（支持直接发送图片、回复图片消息、引用消息中的图片，支持批量导入）"""
    
    success_count, fail_count, skip_count, imported_names, fail_reasons = await _process_character_images(
        event, bot, save_as_global=False
    )
    
    if fail_reasons and fail_reasons[0] == "未找到图片":
        await import_persona_cmd.finish("请发送 PNG 格式的角色卡图片\n\n支持方式：\n1. 直接发送「导入角色卡」并附带 PNG 图片\n2. 回复包含 PNG 图片的消息并发送「导入角色卡」\n3. 引用消息中的 PNG 图片并发送「导入角色卡」\n\n支持格式：TavernAI / SillyTavern PNG 角色卡")
        return
    
    # 计算总图片数
    total_images = success_count + fail_count + skip_count
    
    msg = _build_import_result_message(
        success_count, fail_count, skip_count, imported_names, fail_reasons, total_images, is_global=False
    )
    await import_persona_cmd.finish(msg)


# ========== 导入全局角色卡命令（超级用户） ==========
import_global_persona_cmd = sv.on_command('导入全局角色卡', aliases=('导入全局人格', '加载全局角色卡'), permission=SUPERUSER, only_group=False)

@import_global_persona_cmd.handle()
async def import_global_persona(bot: Bot, event: Event):
    """从 PNG 图片导入角色卡到全局预设（仅超级用户，支持批量导入）"""
    
    success_count, fail_count, skip_count, imported_names, fail_reasons = await _process_character_images(
        event, bot, save_as_global=True
    )
    
    if fail_reasons and fail_reasons[0] == "未找到图片":
        await import_global_persona_cmd.finish("请发送 PNG 格式的角色卡图片\n\n支持方式：\n1. 直接发送「导入全局角色卡」并附带 PNG 图片\n2. 回复包含 PNG 图片的消息并发送「导入全局角色卡」\n3. 引用消息中的 PNG 图片并发送「导入全局角色卡」\n\n支持格式：TavernAI / SillyTavern PNG 角色卡")
        return
    
    # 计算总图片数
    total_images = success_count + fail_count + skip_count
    
    msg = _build_import_result_message(
        success_count, fail_count, skip_count, imported_names, fail_reasons, total_images, is_global=True
    )
    await import_global_persona_cmd.finish(msg)
