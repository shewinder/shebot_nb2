"""MCP 管理命令（超管）"""
from hoshino import Bot, Event
from hoshino.config import save_plugin_config
from hoshino.permission import SUPERUSER

from ..config import Config
from ..mcp import mcp_server_manager
from ..service import sv

conf = Config.get_instance('aichat')

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
