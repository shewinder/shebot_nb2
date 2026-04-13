"""
MCP 系统元工具
提供给 AI 使用的 MCP server 发现和激活功能
"""
from typing import Any, Dict, Optional, TYPE_CHECKING
from loguru import logger

from ..registry import tool_registry, ok, fail

if TYPE_CHECKING:
    from hoshino import Bot, Event
    from ...session import Session


@tool_registry.register(
    name="activate_mcp_server",
    description="""激活指定的 MCP server，使其工具在当前会话中可用。

当用户需要 MCP server 提供的功能时（如浏览器自动化、文件系统操作等），调用此工具激活。

## 参数说明
- server_id: 要激活的 MCP server ID（如 "playwright", "filesystem" 等）

## 使用场景
1. 用户说"帮我截图百度首页" -> 激活 playwright MCP server
2. 用户说"读取这个文件" -> 激活 filesystem MCP server
3. 用户说"搜索这个数据库" -> 激活 database MCP server

## 激活流程
1. 检查 MCP server 是否存在且已启用
2. 连接到 MCP server
3. 将 server 标记为激活状态
4. 该 server 的工具在当前会话中可用

## 注意事项
- 已激活的 MCP server 在当前会话中持续有效
- 单个会话最多激活 3 个 MCP server（防止上下文膨胀）
- 如果 MCP server 禁用自动触发（auto_trigger=false），会返回错误
- 激活后，AI 可以立即使用该 server 的工具

## 示例
activate_mcp_server(server_id="playwright")
""",
    parameters={
        "type": "object",
        "properties": {
            "server_id": {
                "type": "string",
                "description": "要激活的 MCP server ID"
            }
        },
        "required": ["server_id"]
    }
)
async def activate_mcp_server(
    server_id: str,
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    """激活指定 MCP server
    
    Args:
        server_id: MCP server ID
        session: 当前会话（自动注入）
        
    Returns:
        激活结果
    """
    from ...config import Config
    from ...mcp import mcp_session_manager, mcp_server_manager
    
    conf = Config.get_instance('aichat')
    
    if not conf.enable_mcp:
        return fail(
            "MCP 系统未启用",
            error="MCP system disabled"
        )
    
    if not session:
        return fail(
            "无法获取当前会话信息",
            error="Missing session context"
        )
    
    server_id = server_id.strip()
    if not server_id:
        return fail(
            "请提供 MCP server ID",
            error="Missing server_id"
        )
    
    # 检查 MCP server 是否存在
    config = mcp_server_manager.get_server_config(server_id)
    if not config:
        # 尝试查找相似名称
        all_servers = mcp_server_manager.list_server_metadata()
        similar = [s["id"] for s in all_servers 
                   if server_id.lower() in s["id"].lower()]
        
        if similar:
            return fail(
                f"MCP server '{server_id}' 不存在。您是否想找：{', '.join(similar)}？",
                error=f"Server not found, similar: {similar}"
            )
        else:
            available = [s["id"] for s in all_servers]
            return fail(
                f"MCP server '{server_id}' 不存在。可用 server：{', '.join(available) or '无'}",
                error="Server not found"
            )
    
    # 检查是否启用
    if not config.enabled:
        return fail(
            f"MCP server '{server_id}' 已禁用",
            error="Server disabled"
        )
    
    # 检查是否允许 AI 自动触发
    if not config.auto_trigger:
        return fail(
            f"MCP server '{server_id}' 禁止 AI 自动触发，请让用户手动激活",
            error="Auto trigger disabled for this server"
        )
    
    # 检查是否已激活
    if mcp_session_manager.is_server_active(session.session_id, server_id):
        return ok(
            f"MCP server '{server_id}' 已经激活\n\n描述：{config.description or config.name}",
            metadata={
                "server_id": server_id,
                "already_active": True,
                "description": config.description,
                "name": config.name
            }
        )
    
    # 检查是否超过最大数量
    active_count = len(mcp_session_manager.get_active_servers(session.session_id))
    if active_count >= mcp_session_manager.MAX_SERVERS_PER_SESSION:
        return fail(
            f"当前会话已激活 {active_count} 个 MCP server，达到上限（{mcp_session_manager.MAX_SERVERS_PER_SESSION}）。"
            f"请先停用其他 server。",
            error="Max servers reached"
        )
    
    try:
        # 激活 MCP server（会触发连接）
        success, message = await mcp_session_manager.activate_server(
            session.session_id, 
            server_id
        )
        
        if success:
            # 获取该 server 的工具列表
            tools = await mcp_server_manager.get_tools_for_servers({server_id})
            tool_names = [t["name"] for t in tools]
            
            # 构建 MCP 工具调用名称示例
            mcp_tool_examples = []
            for name in tool_names[:5]:
                mcp_tool_name = f"mcp_{server_id}_{name.replace('-', '_').replace('.', '_')}"
                mcp_tool_examples.append(f"  - {mcp_tool_name}")
            
            result_lines = [
                f"✅ {message}",
                f"",
                f"📖 描述：{config.description or config.name}",
                f"",
                f"🔧 可用 MCP 工具（共 {len(tool_names)} 个）：",
            ]
            
            if tool_names:
                result_lines.append(f"  原始名称：{', '.join(tool_names[:10])}")
                if len(tool_names) > 10:
                    result_lines.append(f"  ... 等共 {len(tool_names)} 个")
                
                result_lines.extend([
                    f"",
                    f"📌 重要：MCP 工具的调用格式为：",
                    f"  mcp_{server_id}_<工具名称>",
                    f"",
                    f"例如：",
                ])
                result_lines.extend(mcp_tool_examples)
                
                if len(tool_names) > 5:
                    result_lines.append(f"  ... 等共 {len(tool_names)} 个工具")
                
                result_lines.extend([
                    f"",
                    f"⚠️ 注意：这些是 MCP 工具，不是 SKILL 工具！",
                    f"不要调用 execute_script，直接使用上述 mcp_ 开头的工具名称。",
                ])
            
            return ok(
                "\n".join(result_lines),
                metadata={
                    "server_id": server_id,
                    "already_active": False,
                    "description": config.description,
                    "name": config.name,
                    "tool_count": len(tool_names),
                    "tool_names": tool_names[:20],  # 最多返回 20 个
                    "mcp_tool_prefix": f"mcp_{server_id}_"
                }
            )
        else:
            return fail(
                f"激活 MCP server 失败：{message}",
                error=message
            )
            
    except Exception as e:
        logger.exception(f"activate_mcp_server 执行失败: {e}")
        return fail(f"激活 MCP server 失败: {str(e)}", error=str(e))


@tool_registry.register(
    name="list_active_mcp_servers",
    description="""列出当前会话中已激活的 MCP server。

用于查询当前有哪些 MCP server 已经激活，以及它们提供的工具。

## 使用场景
1. AI 需要确认某个 MCP server 是否已激活
2. 用户询问"现在有哪些 MCP 工具可用"
3. 诊断 MCP 状态

## 示例
list_active_mcp_servers()
""",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
async def list_active_mcp_servers(
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    """列出当前会话中已激活的 MCP server
    
    Args:
        session: 当前会话（自动注入）
        
    Returns:
        已激活 server 列表
    """
    from ...config import Config
    from ...mcp import mcp_session_manager, mcp_server_manager
    
    conf = Config.get_instance('aichat')
    
    if not conf.enable_mcp:
        return fail(
            "MCP 系统未启用",
            error="MCP system disabled"
        )
    
    if not session:
        return fail(
            "无法获取当前会话信息",
            error="Missing session context"
        )
    
    try:
        active_servers = mcp_session_manager.get_active_servers(session.session_id)
        
        if not active_servers:
            all_servers = mcp_server_manager.list_server_metadata()
            available = [s["id"] for s in all_servers if s.get("auto_trigger")]
            return ok(
                f"当前会话没有激活的 MCP server。\n"
                f"可用 server：{', '.join(available) or '无'}\n"
                f"使用 activate_mcp_server(server_id=\"xxx\") 激活。",
                metadata={
                    "active_servers": [],
                    "count": 0,
                    "available_servers": available
                }
            )
        
        # 构建详细信息
        server_details = []
        for server_id in active_servers:
            config = mcp_server_manager.get_server_config(server_id)
            tools = await mcp_server_manager.get_tools_for_servers({server_id})
            tool_names = [t["name"] for t in tools]
            
            server_details.append({
                "id": server_id,
                "name": config.name if config else server_id,
                "description": config.description if config else "",
                "tool_count": len(tool_names),
                "tools": tool_names[:10]  # 最多显示 10 个
            })
        
        lines = [f"当前已激活 {len(active_servers)} 个 MCP server："]
        for detail in server_details:
            lines.append(f"\n• {detail['id']}: {detail['description'] or detail['name']}")
            lines.append(f"  工具 ({detail['tool_count']} 个): {', '.join(detail['tools'])}")
        
        return ok(
            "\n".join(lines),
            metadata={
                "active_servers": server_details,
                "count": len(active_servers)
            }
        )
        
    except Exception as e:
        logger.exception(f"list_active_mcp_servers 执行失败: {e}")
        return fail(f"查询失败: {str(e)}", error=str(e))
