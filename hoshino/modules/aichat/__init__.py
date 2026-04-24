"""AI Chat 插件"""
import asyncio
from typing import Tuple, List, Optional, Set
from loguru import logger
from hoshino import Bot, Event, Service
from hoshino.permission import ADMIN, SUPERUSER
from hoshino.typing import T_State

from .aichat.api import api_manager
from .aichat.chat import handle_ai_chat
from .aichat.character_import import parse_character_png
from .aichat.config import Config
from .aichat.persona import persona_manager
from .aichat.session import Session, SessionManager, session_manager
from hoshino.util import aiohttpx, get_event_imageurl
from hoshino.util.message_util import extract_images_from_reply

# MCP 导入
from .aichat.mcp import mcp_server_manager, mcp_tool_bridge

# SKILL 系统导入
from .aichat.skills import skill_manager

conf = Config.get_instance('aichat')


# MCP 初始化函数
async def init_mcp_servers():
    """初始化 MCP servers（预连接 + 渐进式注入）
    
    启动时连接所有启用的 MCP server，确保首次激活时无延迟。
    但工具只在激活后才注入到对话中（渐进式注入）。
    """
    if not conf.enable_mcp:
        logger.info("MCP 功能已禁用")
        return
    
    if not conf.mcp_servers:
        logger.info("未配置 MCP servers")
        return
    
    logger.info(f"正在初始化 MCP servers，共 {len(conf.mcp_servers)} 个配置")
    
    try:
        # 1. 初始化 server_manager（只保存配置）
        mcp_server_manager.initialize(conf.mcp_servers)
        
        # 2. 创建并初始化 session_manager
        from .mcp import init_mcp_session_manager
        init_mcp_session_manager()
        
        # 3. 预连接所有启用的 server（确保首次激活无延迟）
        logger.info("正在预连接所有 MCP servers...")
        connect_tasks = []
        for server_config in conf.mcp_servers:
            if server_config.enabled:
                task = _connect_server_with_timeout(server_config)
                connect_tasks.append((server_config.id, task))
        
        # 并行连接，设置超时
        connected_count = 0
        failed_servers = []
        for server_id, task in connect_tasks:
            try:
                success = await asyncio.wait_for(task, timeout=30)
                if success:
                    connected_count += 1
                    logger.info(f"MCP server '{server_id}' 预连接成功")
                else:
                    failed_servers.append(server_id)
                    logger.warning(f"MCP server '{server_id}' 预连接失败")
            except asyncio.TimeoutError:
                failed_servers.append(server_id)
                logger.warning(f"MCP server '{server_id}' 预连接超时")
            except Exception as e:
                failed_servers.append(server_id)
                logger.exception(f"MCP server '{server_id}' 预连接异常: {e}")
        
        logger.info(f"MCP 系统初始化完成：{connected_count}/{len(connect_tasks)} 个 server 已连接")
        if failed_servers:
            logger.warning(f"连接失败的 servers: {', '.join(failed_servers)}（将在激活时重试）")
        
    except Exception as e:
        logger.exception(f"初始化 MCP 系统失败: {e}")


async def _connect_server_with_timeout(server_config):
    """连接单个 MCP server（带错误处理）"""
    try:
        from .mcp import mcp_server_manager
        return await mcp_server_manager.ensure_connected(server_config.id)
    except asyncio.CancelledError:
        raise
    except Exception:
        return False


# SKILL 系统初始化函数
def init_skill_system():
    """初始化 SKILL 系统"""
    if not conf.enable_skills:
        logger.info("SKILL 系统已禁用")
        return
    
    try:
        skill_manager.user_paths = conf.skill_user_paths
        skill_manager.initialize()
        logger.info(f"SKILL 系统初始化完成，内置路径 + 用户路径: {conf.skill_user_paths}")
    except Exception as e:
        logger.exception(f"初始化 SKILL 系统失败: {e}")


# 注册启动时初始化 MCP 和 SKILL
try:
    from nonebot import get_driver
    driver = get_driver()
    
    @driver.on_startup
    async def _init_mcp():
        await init_mcp_servers()
        # 同时初始化 SKILL 系统
        init_skill_system()
    
    @driver.on_shutdown
    async def _shutdown_mcp():
        await mcp_server_manager.stop_all()
            
except ImportError:
    pass
sv = Service('aichat', help_='''AI聊天插件
基础用法：
  #消息   以#开头触发AI对话
  进入对话模式   进入免#触发模式
  退出对话模式/结束对话模式  退出连续对话模式
  查看对话模式  查看当前模式状态
对话管理：
  清除对话/清空对话/重置对话  清除当前对话历史
  回溯/回退 [N]  回溯N条对话
  查询token/token查询  查询当前会话的 Token 使用情况
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
  切换模型  进入模型切换流程，自动获取可用模型列表（超管）
工具功能（需要模型支持 Tool Calling）：
  支持画图、搜索、定时任务等工具调用
  注意：在 config 中设置 supports_tools=true 启用
定时任务（通过AI对话创建）：
  说"帮我创建一个定时任务，每天早上8点..."即可
  AI会自动调用 schedule_task 工具创建
  支持：创建/查看/暂停/删除任务
角色卡：
  导入角色卡 [图片]  从PNG角色卡导入人格
  导入全局角色卡 [图片]  导入全局预设人格（超管）
预设人格（超管）：
  预设人格 [名称] [描述]  添加/更新预设人格
  预设人格列表  列出全局预设人格
  删除预设人格 [名称]  删除预设人格
SKILL 系统：
  #使用 <skill名称>  激活指定 SKILL
  #技能列表  列出所有可用 SKILL
  #当前技能  查看已激活的 SKILL
  #停用技能 <skill名称>  停用指定 SKILL
  #停用所有技能  停用所有 SKILL
''')

sv.on_message(priority=10, block=False, only_group=False).handle()(handle_ai_chat)

enter_chat_mode_cmd = sv.on_command('进入对话模式', aliases=('连续对话', '免井号对话', '聊天模式', '进入聊天'), only_group=False, block=True)

@enter_chat_mode_cmd.handle()
async def enter_chat_mode(bot: Bot, event: Event):
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    persona = persona_manager.get_persona(user_id, group_id)
    session = session_manager.get_or_create_session(user_id, group_id, persona)
    session.continuous_mode = True
    
    msg = "已进入连续对话模式！\n现在可以直接发送消息，无需 # 前缀即可与AI对话。\n"
    msg += f"当前人格：{persona[:30]}..." if persona else "当前人格：默认"
    msg += "\n\n提示：\n- 发送「退出对话模式」退出此模式\n- 发送「清除对话」清空当前对话历史\n- session过期后将自动退出此模式"
    
    await enter_chat_mode_cmd.finish(msg)


exit_chat_mode_cmd = sv.on_command('退出对话模式', aliases=('退出聊天', '结束对话模式'), only_group=False)

@exit_chat_mode_cmd.handle()
async def exit_chat_mode(bot: Bot, event: Event):
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    session = session_manager.get_session(user_id, group_id)
    was_in_mode = session.continuous_mode if session else False
    
    if not was_in_mode:
        await exit_chat_mode_cmd.finish("你当前不在连续对话模式中，发送「进入对话模式」来开启")
        return
    
    # 退出连续对话模式
    if session:
        session.continuous_mode = False
    await exit_chat_mode_cmd.finish("已退出连续对话模式。\n现在需要使用 # 前缀来触发AI对话。")


check_chat_mode_cmd = sv.on_command('查看对话模式', aliases=('对话模式状态',), only_group=False)

@check_chat_mode_cmd.handle()
async def check_chat_mode(bot: Bot, event: Event):
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    session = session_manager.get_session(user_id, group_id)
    in_mode = session.continuous_mode if session else False
    
    if in_mode:
        await check_chat_mode_cmd.finish("当前处于「连续对话模式」，直接发送消息即可与AI对话\n发送「退出对话模式」退出此模式")
    else:
        await check_chat_mode_cmd.finish("当前处于「普通模式」，需要使用 # 前缀触发AI对话\n发送「进入对话模式」开启免#触发")


clear_cmd = sv.on_command('清除对话', aliases=('清空对话', '重置对话'), only_group=False)

@clear_cmd.handle()
async def clear_session(bot: Bot, event: Event):
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    if session_manager.clear_session(user_id, group_id):
        await bot.send(event, "对话历史已清除")
    else:
        await bot.send(event, "没有找到对话历史")


rollback_cmd = sv.on_command('回溯', aliases=('回退', '删除对话', '返回'), only_group=False, block=True)

@rollback_cmd.handle()
async def rollback_session(bot: Bot, event: Event):
    args = str(event.message).strip().split()
    
    count = 1  # 默认回溯1条
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
    
    session = session_manager.get_session(user_id, group_id)
    if not session:
        await rollback_cmd.finish("没有可回溯的对话记录")
        return
    
    deleted, actual_rounds = session.rollback_messages(count)
    
    if deleted == 0:
        await rollback_cmd.finish("没有可回溯的对话记录")
    elif actual_rounds < count:
        await rollback_cmd.finish(f"已回溯 {actual_rounds} 条对话（共删除 {deleted} 条消息，历史记录不足）")
    else:
        await rollback_cmd.finish(f"已回溯 {actual_rounds} 条对话（共删除 {deleted} 条消息）")


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


switch_api_cmd = sv.on_command('切换API', aliases=('切换厂商', '选择API', '切换api'), permission=SUPERUSER, only_group=False)

@switch_api_cmd.handle()
async def switch_api(bot: Bot, event: Event):
    args = str(event.message).strip().split(maxsplit=1)
    apis = conf.get_apis()
    if not apis:
        await switch_api_cmd.finish("未配置任何 API 厂商，请联系管理员在 config/aichat.json 中配置 apis")
        return
    
    current_api = api_manager.get_current_api()
    
    if len(args) < 2:
        lines = ["可用 API 厂商："]
        for i, a in enumerate(apis, 1):
            mark = " (当前)" if a.api == current_api else ""
            lines.append(f"{i}. {a.api}{mark} - 模型: {a.model}")
        lines.append("\n请使用「切换API 厂商名」切换")
        await switch_api_cmd.finish("\n".join(lines))
        return
    
    api_input = args[1].strip()
    
    target = None
    for a in apis:
        if a.api.lower() == api_input.lower():
            target = a
            break
    
    
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


switch_model_cmd = sv.on_command('切换模型', aliases=('选择模型', '设置模型'), permission=SUPERUSER, only_group=False)

@switch_model_cmd.handle()
async def switch_model_handle(bot: Bot, event: Event, state: T_State):
    args: List[str] = str(event.message).strip().split(maxsplit=1)
    
    current_api: str = api_manager.get_current_api()
    old_model: str = api_manager.get_current_model()
    
    if len(args) >= 2:
        target_model: str = args[1].strip()
        if api_manager.set_current_model(target_model):
            await switch_model_cmd.finish(f"已切换模型：{old_model} → {target_model}\n当前 API 厂商：{current_api}")
        else:
            await switch_model_cmd.finish("切换模型失败")
        return
    
    
    state['current_api'] = current_api
    state['old_model'] = old_model
    await switch_model_cmd.send(f"当前 API 厂商：{current_api}\n当前模型：{old_model}\n请发送要切换的模型名称")

@switch_model_cmd.got('model_name')
async def switch_model_got(bot: Bot, event: Event, state: T_State):
    model_name: str = str(state['model_name']).strip()
    
    if model_name in ['取消', 'cancel', 'q']:
        await switch_model_cmd.finish("已取消切换模型")
        return
    
    current_api: str = state.get('current_api', '')
    old_model: str = state.get('old_model', '')
    
    if api_manager.set_current_model(model_name):
        await switch_model_cmd.finish(f"已切换模型：{old_model} → {model_name}\n当前 API 厂商：{current_api}")
    else:
        await switch_model_cmd.finish("切换模型失败")


search_model_cmd = sv.on_command('搜索模型', aliases=('查找模型', '模型列表'), only_group=False)

@search_model_cmd.handle()
async def search_model_handle(bot: Bot, event: Event):
    args: List[str] = str(event.message).strip().split(maxsplit=1)
    keyword: Optional[str] = args[1].strip().lower() if len(args) >= 2 else None
    
    current_api: str = api_manager.get_current_api()
    current_model: str = api_manager.get_current_model()
    
    models: List[str] = await api_manager.get_available_models()
    if not models:
        await search_model_cmd.finish(f"无法获取 {current_api} 的模型列表")
        return
    
    filtered_models: List[str] = models
    if keyword:
        filtered_models = [m for m in models if keyword in m.lower()]
    
    if not filtered_models:
        await search_model_cmd.finish(f"未找到包含「{keyword}」的模型\n当前 API 厂商：{current_api}")
        return
    
    
    prefix: str = f"包含「{keyword}」的" if keyword else ""
    lines: List[str] = [f"{current_api} {prefix}模型（共 {len(filtered_models)} 个）："]
    
    display_models: List[str] = filtered_models[:30]
    for i, m in enumerate(display_models, 1):
        mark: str = " ★当前" if m == current_model else ""
        lines.append(f"{i}. {m}{mark}")
    
    if len(filtered_models) > 30:
        lines.append(f"... 还有 {len(filtered_models) - 30} 个模型")
    
    lines.append(f"\n当前模型：{current_model}")
    lines.append("使用「切换模型 <模型名>」进行切换")
    
    await search_model_cmd.finish("\n".join(lines))



current_model_cmd = sv.on_command('当前模型', aliases=('查看模型', '当前大模型'), only_group=False)

@current_model_cmd.handle()
async def current_model(bot: Bot, event: Event):
    api_name = api_manager.get_current_api()
    model_name = api_manager.get_current_model()
    
    lines = [
        f"🤖 当前 API 厂商：{api_name}",
        f"💬 对话模型：{model_name}",
    ]
    
    await current_model_cmd.finish("\n".join(lines))



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


async def _process_character_images(event: Event, bot: Bot, save_as_global: bool = False) -> Tuple[int, int, int, list, list]:
    image_urls = get_event_imageurl(event)
    
    try:
        image_urls.extend(await extract_images_from_reply(event, bot))
    except Exception as e:
        logger.debug(f"提取引用消息图片失败: {e}")
    
    if not image_urls:
        return 0, 0, 0, [], ["未找到图片"]
    
    
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    success_count = 0
    fail_count = 0
    skip_count = 0
    imported_names = []
    fail_reasons = []
    
    for i, image_url in enumerate(image_urls, 1):
        try:
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
            
            success, char_card, msg = parse_character_png(image_data)
            
            if not success or not char_card:
                skip_count += 1
                logger.debug(f"第{i}张图片不是有效的角色卡：{msg}")
                continue
            
            persona_name = char_card.name
            persona_text = char_card.to_persona_text()
            
            if save_as_global:
                success_save, msg_save = persona_manager.add_global_preset(persona_name, persona_text)
            else:
                success_save, msg_save = persona_manager.save_persona(user_id, group_id, persona_name, persona_text)
            
            if success_save:
                success_count += 1
                imported_names.append(persona_name)
            else:
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



import_persona_cmd = sv.on_command('导入角色卡', aliases=('导入人格', '加载角色卡'), only_group=False)

@import_persona_cmd.handle()
async def import_persona(bot: Bot, event: Event):
    
    success_count, fail_count, skip_count, imported_names, fail_reasons = await _process_character_images(
        event, bot, save_as_global=False
    )
    
    if fail_reasons and fail_reasons[0] == "未找到图片":
        await import_persona_cmd.finish("请发送 PNG 格式的角色卡图片\n\n支持方式：\n1. 直接发送「导入角色卡」并附带 PNG 图片\n2. 回复包含 PNG 图片的消息并发送「导入角色卡」\n3. 引用消息中的 PNG 图片并发送「导入角色卡」\n\n支持格式：TavernAI / SillyTavern PNG 角色卡")
        return
    
    total_images = success_count + fail_count + skip_count
    
    msg = _build_import_result_message(
        success_count, fail_count, skip_count, imported_names, fail_reasons, total_images, is_global=False
    )
    await import_persona_cmd.finish(msg)



import_global_persona_cmd = sv.on_command('导入全局角色卡', aliases=('导入全局人格', '加载全局角色卡'), permission=SUPERUSER, only_group=False)

@import_global_persona_cmd.handle()
async def import_global_persona(bot: Bot, event: Event):
    
    success_count, fail_count, skip_count, imported_names, fail_reasons = await _process_character_images(
        event, bot, save_as_global=True
    )
    
    if fail_reasons and fail_reasons[0] == "未找到图片":
        await import_global_persona_cmd.finish("请发送 PNG 格式的角色卡图片\n\n支持方式：\n1. 直接发送「导入全局角色卡」并附带 PNG 图片\n2. 回复包含 PNG 图片的消息并发送「导入全局角色卡」\n3. 引用消息中的 PNG 图片并发送「导入全局角色卡」\n\n支持格式：TavernAI / SillyTavern PNG 角色卡")
        return
    
    total_images = success_count + fail_count + skip_count
    
    msg = _build_import_result_message(
        success_count, fail_count, skip_count, imported_names, fail_reasons, total_images, is_global=True
    )
    await import_global_persona_cmd.finish(msg)



# ========== MCP 管理命令 ==========

mcp_list_cmd = sv.on_command('MCP列表', aliases=('列出MCP', 'MCP状态'), permission=SUPERUSER, only_group=False)

@mcp_list_cmd.handle()
async def mcp_list(bot: Bot, event: Event):
    """列出所有 MCP server 状态"""
    if not conf.enable_mcp:
        await mcp_list_cmd.finish("MCP 功能未启用，请在配置中设置 enable_mcp: true")
        return
    
    servers = mcp_server_manager.list_servers()
    
    if not servers:
        await mcp_list_cmd.finish("未配置 MCP servers\n\n使用说明：\n在 data/config/aichat.json 中添加 mcp_servers 配置")
        return
    
    lines = [f"📡 MCP Servers（共 {len(servers)} 个）：\n"]
    
    for server in servers:
        status = "🟢 已连接" if server["connected"] else "🔴 未连接"
        enabled = "启用" if server["enabled"] else "禁用"
        lines.append(f"• {server['name']} ({server['id']})")
        lines.append(f"  状态：{status} | {enabled}")
        lines.append(f"  工具数：{server['tool_count']} | 传输：{server['transport']}")
        lines.append("")
    
    lines.append("管理命令：")
    lines.append("• MCP启用 <id> - 启用指定 server")
    lines.append("• MCP禁用 <id> - 禁用指定 server")
    lines.append("• MCP重启 <id> - 重启指定 server")
    lines.append("• MCP工具 - 列出所有可用工具")
    
    await mcp_list_cmd.finish("\n".join(lines))


mcp_enable_cmd = sv.on_command('MCP启用', aliases=('启用MCP', '开启MCP'), permission=SUPERUSER, only_group=False)

@mcp_enable_cmd.handle()
async def mcp_enable(bot: Bot, event: Event):
    """启用指定 MCP server"""
    if not conf.enable_mcp:
        await mcp_enable_cmd.finish("MCP 功能未启用")
        return
    
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await mcp_enable_cmd.finish("请提供 MCP server ID，例如：MCP启用 filesystem")
        return
    
    server_id = args[1].strip()
    
    # 查找配置
    server_config = None
    for sc in conf.mcp_servers:
        if sc.id == server_id:
            server_config = sc
            break
    
    if not server_config:
        await mcp_enable_cmd.finish(f"未找到 ID 为 '{server_id}' 的 MCP server 配置")
        return
    
    # 如果已存在，先移除再重新添加
    if server_id in mcp_server_manager._clients:
        await mcp_server_manager.stop_server(server_id)
        mcp_server_manager.remove_server(server_id)
    
    server_config.enabled = True
    mcp_server_manager.add_server(server_config)
    success = await mcp_server_manager.start_server(server_id)
    
    # 保存配置状态
    from hoshino.config import save_plugin_config
    save_plugin_config("aichat", conf)
    
    if success:
        await mcp_enable_cmd.finish(f"✅ MCP server '{server_id}' 已启用并连接")
    else:
        await mcp_enable_cmd.finish(f"⚠️ MCP server '{server_id}' 启用但连接失败，请检查日志")


mcp_disable_cmd = sv.on_command('MCP禁用', aliases=('禁用MCP', '关闭MCP'), permission=SUPERUSER, only_group=False)

@mcp_disable_cmd.handle()
async def mcp_disable(bot: Bot, event: Event):
    """禁用指定 MCP server"""
    if not conf.enable_mcp:
        await mcp_disable_cmd.finish("MCP 功能未启用")
        return
    
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await mcp_disable_cmd.finish("请提供 MCP server ID，例如：MCP禁用 filesystem")
        return
    
    server_id = args[1].strip()
    
    if server_id not in mcp_server_manager._clients:
        await mcp_disable_cmd.finish(f"MCP server '{server_id}' 未运行")
        return
    
    await mcp_server_manager.stop_server(server_id)
    mcp_server_manager.remove_server(server_id)
    
    # 更新配置中的启用状态
    for server_config in conf.mcp_servers:
        if server_config.id == server_id:
            server_config.enabled = False
            from hoshino.config import save_plugin_config
            save_plugin_config("aichat", conf)
            break
    
    await mcp_disable_cmd.finish(f"✅ MCP server '{server_id}' 已禁用")


mcp_restart_cmd = sv.on_command('MCP重启', aliases=('重启MCP'), permission=SUPERUSER, only_group=False)

@mcp_restart_cmd.handle()
async def mcp_restart(bot: Bot, event: Event):
    """重启指定 MCP server"""
    if not conf.enable_mcp:
        await mcp_restart_cmd.finish("MCP 功能未启用")
        return
    
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await mcp_restart_cmd.finish("请提供 MCP server ID，例如：MCP重启 filesystem")
        return
    
    server_id = args[1].strip()
    
    # 查找配置
    server_config = None
    for sc in conf.mcp_servers:
        if sc.id == server_id:
            server_config = sc
            break
    
    if not server_config:
        await mcp_restart_cmd.finish(f"未找到 ID 为 '{server_id}' 的 MCP server 配置")
        return
    
    # 重启
    if server_id in mcp_server_manager._clients:
        await mcp_server_manager.stop_server(server_id)
        mcp_server_manager.remove_server(server_id)
    
    server_config.enabled = True
    mcp_server_manager.add_server(server_config)
    success = await mcp_server_manager.start_server(server_id)
    
    if success:
        tools = mcp_server_manager.get_server(server_id).tools
        await mcp_restart_cmd.finish(f"✅ MCP server '{server_id}' 重启成功，发现 {len(tools)} 个工具")
    else:
        await mcp_restart_cmd.finish(f"❌ MCP server '{server_id}' 重启失败，请检查日志")


mcp_tools_cmd = sv.on_command('MCP工具', aliases=('MCP工具列表', '列出MCP工具'), permission=SUPERUSER, only_group=False)

@mcp_tools_cmd.handle()
async def mcp_tools(bot: Bot, event: Event):
    """列出所有可用的 MCP 工具"""
    if not conf.enable_mcp:
        await mcp_tools_cmd.finish("MCP 功能未启用")
        return
    
    all_tools = await mcp_server_manager.get_all_tools()
    
    if not all_tools:
        await mcp_tools_cmd.finish("暂无可用的 MCP 工具\n\n请确保：\n1. 已配置 MCP servers\n2. Servers 已连接（使用 'MCP列表' 查看状态）")
        return
    
    # 按 server 分组
    tools_by_server: dict = {}
    for tool in all_tools:
        server_id = tool["server_id"]
        if server_id not in tools_by_server:
            tools_by_server[server_id] = {
                "name": tool["server_name"],
                "tools": []
            }
        tools_by_server[server_id]["tools"].append(tool)
    
    lines = [f"🔧 MCP 工具列表（共 {len(all_tools)} 个）：\n"]
    
    for server_id, data in tools_by_server.items():
        lines.append(f"📦 {data['name']} ({server_id})：")
        for tool in data["tools"]:
            desc = tool.get("description", "")[:50]
            if len(tool.get("description", "")) > 50:
                desc += "..."
            lines.append(f"  • {tool['name']}: {desc}")
        lines.append("")
    
    lines.append("💡 提示：MCP 工具会自动暴露给 AI 使用，无需额外配置")
    
    await mcp_tools_cmd.finish("\n".join(lines))


# ========== SKILL 系统命令 ==========

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
        model_invocation = "🤖" if not skill.metadata.disable_model_invocation else "🚫"
        user_invocable = "👤" if skill.metadata.user_invocable else "🚫"
        lines.append(f"• {skill.metadata.name}")
        lines.append(f"  {model_invocation}AI可触发 {user_invocable}用户可触发")
        lines.append(f"  📖 {skill.metadata.description}")
        if skill.metadata.allowed_tools:
            lines.append(f"  🔧 {', '.join(skill.metadata.allowed_tools)}")
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


# ========== Token 查询命令 ==========

query_token_cmd = sv.on_command('查询token', aliases=('token查询', 'token统计', 'token使用'), only_group=False)

@query_token_cmd.handle()
async def query_token(bot: Bot, event: Event):
    """查询当前 session 的 token 使用情况"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    session = session_manager.get_session(user_id, group_id)
    
    if not session or session.total_tokens == 0:
        await query_token_cmd.finish("📊 当前会话暂无 token 使用记录\n\n提示：\n- 请先与 AI 进行对话\n- Token 统计在 session 过期后重置")
        return
    
    lines = [
        "📊 当前会话 Token 使用情况：\n",
        f"💬 输入 Token：{session.total_prompt_tokens:,}",
        f"🤖 输出 Token：{session.total_completion_tokens:,}",
        f"📈 总计 Token：{session.total_tokens:,}",
        "\n注：Token 统计在 session 过期后重置",
    ]
    
    await query_token_cmd.finish("\n".join(lines))
