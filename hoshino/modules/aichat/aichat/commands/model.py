"""API/模型/子 Agent 配置命令"""
from typing import List, Optional

from hoshino import Bot, Event
from hoshino.config import save_plugin_config
from hoshino.permission import SUPERUSER
from hoshino.typing import T_State

from ..api import api_manager
from ..config import Config
from ..service import sv

conf = Config.get_instance('aichat')

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

    if not target:
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

    if conf.subagent_profiles:
        lines.append(f"\n📦 子 Agent 模型配置：")
        for p in conf.subagent_profiles:
            model_display = p.model
            if not model_display and p.api:
                entry = conf.get_api_by_name(p.api)
                model_display = entry.model if entry else "默认"
            mm = "🖼️" if p.supports_multimodal else ""
            lines.append(f"  · {p.name}: {model_display} ({p.api}) {mm}")

    await current_model_cmd.finish("\n".join(lines))


subapi_cmd = sv.on_command('切换subapi', permission=SUPERUSER, only_group=False)


@subapi_cmd.handle()
async def subapi(bot: Bot, event: Event):
    """切换子Agent的API厂商"""
    if not conf.subagent_profiles:
        await subapi_cmd.finish("当前没有子Agent 配置")

    args = str(event.message).strip().split(maxsplit=2)
    apis = conf.get_apis()

    if len(args) < 2:
        # 无参数：列出所有 profile 及当前 API
        lines = ["📦 子Agent 配置："]
        for p in conf.subagent_profiles:
            lines.append(f"  · {p.name}: API={p.api or '(继承主API)'}")
        lines.append(f"\n使用「切换subapi <name> [api]」切换")
        await subapi_cmd.finish("\n".join(lines))
        return

    name = args[1].strip()

    # 查找 profile
    target = None
    for p in conf.subagent_profiles:
        if p.name == name:
            target = p
            break

    if not target:
        available = ", ".join(p.name for p in conf.subagent_profiles)
        await subapi_cmd.finish(f"未找到名为 '{name}' 的子Agent 配置\n当前可用：{available}")
        return

    if len(args) < 3:
        # 只给了 name：列出可选 API
        lines = [f"子Agent「{name}」当前 API：{target.api or '(继承主API)'}"]
        lines.append(f"\n可用 API 厂商：")
        for i, a in enumerate(apis, 1):
            mark = " ★当前" if a.api == target.api else ""
            lines.append(f"  {i}. {a.api}{mark} - {a.model}")
        lines.append(f"\n使用「切换subapi {name} <api>」切换")
        await subapi_cmd.finish("\n".join(lines))
        return

    api_input = args[2].strip()

    # 校验厂商
    entry = None
    for a in apis:
        if a.api.lower() == api_input.lower():
            entry = a
            break

    if not entry:
        try:
            idx = int(api_input) - 1
            if 0 <= idx < len(apis):
                entry = apis[idx]
        except ValueError:
            pass

    if not entry:
        available = ", ".join(a.api for a in apis)
        await subapi_cmd.finish(f"未找到 API 厂商「{api_input}」\n可用：{available}")
        return

    old_api = target.api
    target.api = entry.api
    target.model = entry.model  # 切 API 时自动跟进默认 model

    save_plugin_config("aichat", conf)

    await subapi_cmd.finish(
        f"子Agent「{name}」API 已切换：{old_api or '(默认)'} → {entry.api}\n"
        f"模型自动切换为：{entry.model}"
    )


submodel_cmd = sv.on_command('切换submodel', permission=SUPERUSER, only_group=False)


@submodel_cmd.handle()
async def submodel_handle(bot: Bot, event: Event, state: T_State):
    """切换子Agent的模型"""
    if not conf.subagent_profiles:
        await submodel_cmd.finish("当前没有子Agent 配置")

    args = str(event.message).strip().split(maxsplit=2)

    if len(args) < 2:
        lines = ["📦 子Agent 配置："]
        for p in conf.subagent_profiles:
            model_display = p.model
            if not model_display and p.api:
                entry = conf.get_api_by_name(p.api)
                model_display = f"(继承: {entry.model})" if entry else "(继承主API)"
            elif not model_display:
                model_display = "(继承主API)"
            lines.append(f"  · {p.name}: {model_display}")
        lines.append(f"\n使用「切换submodel <name> [model]」切换")
        await submodel_cmd.finish("\n".join(lines))
        return

    name = args[1].strip()

    target = None
    for p in conf.subagent_profiles:
        if p.name == name:
            target = p
            break

    if not target:
        available = ", ".join(p.name for p in conf.subagent_profiles)
        await submodel_cmd.finish(f"未找到名为 '{name}' 的子Agent 配置\n当前可用：{available}")
        return

    if len(args) >= 3:
        # 有 model 参数：直接设置
        model_name = args[2].strip()
        old_model = target.model or "(继承)"
        target.model = model_name

        save_plugin_config("aichat", conf)

        await submodel_cmd.finish(f"子Agent「{name}」模型已切换：{old_model} → {model_name}")
        return

    # 无 model 参数：进入交互流程
    state['sub_name'] = name
    current = target.model
    if not current and target.api:
        entry = conf.get_api_by_name(target.api)
        current = entry.model if entry else "(继承主API)"
    elif not current:
        current = "(继承主API)"
    await submodel_cmd.send(f"子Agent「{name}」当前模型：{current}\n请发送要切换的模型名称（发送「取消」退出）")


@submodel_cmd.got('model_name')
async def submodel_got(bot: Bot, event: Event, state: T_State):
    model_name: str = str(state['model_name']).strip()

    if model_name in ['取消', 'cancel', 'q']:
        await submodel_cmd.finish("已取消")

    name = state.get('sub_name', '')

    target = None
    for p in conf.subagent_profiles:
        if p.name == name:
            target = p
            break

    if not target:
        await submodel_cmd.finish("配置已变更，请重新操作")

    old_model = target.model or "(继承)"
    target.model = model_name

    save_plugin_config("aichat", conf)

    await submodel_cmd.finish(f"子Agent「{name}」模型已切换：{old_model} → {model_name}")
