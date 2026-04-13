"""MCP (Model Context Protocol) 支持模块

为 aichat 提供 MCP 协议支持，允许连接外部 MCP servers 扩展 AI 能力。
支持渐进式加载：只激活需要的 server，减少资源消耗。

Usage:
    # 导入主要组件
    from .mcp import mcp_server_manager, mcp_session_manager, mcp_tool_bridge
    
    # 配置并初始化（渐进式加载）
    from ..config import Config
    conf = Config.get_instance('aichat')
    
    if conf.enable_mcp:
        # 1. 初始化 server_manager（只保存配置，不连接）
        mcp_server_manager.initialize(conf.mcp_servers)
        
        # 2. 创建 session_manager
        from .mcp import MCPSessionManager
        mcp_session_manager = MCPSessionManager(mcp_server_manager)
        
        # 3. 绑定到 tool_bridge
        mcp_tool_bridge.set_session_manager(mcp_session_manager)
    
    # 获取 MCP server 摘要（用于 AI 选择）
    summary = mcp_tool_bridge.get_metadata_summary()
    
    # 激活 MCP server（在特定会话中）
    success, message = await mcp_session_manager.activate_server(session_id, "playwright")
    
    # 获取激活的工具 schemas
    schemas = await mcp_tool_bridge.get_active_tool_schemas(session_id)
    
    # 调用 MCP 工具
    result = await mcp_tool_bridge.call_mcp_tool("playwright", "browser_navigate", {"url": "..."})
"""

# 配置
from .config import MCPServerConfig

# 客户端
from .client import MCPClient

# 管理器
from .server_manager import MCPServerManager, mcp_server_manager

# 会话管理器（渐进式加载）
from .session_manager import MCPSessionManager

# 工具桥接
from .tool_bridge import MCPToolBridge, mcp_tool_bridge

mcp_session_manager: MCPSessionManager = None  # type: ignore

def init_mcp_session_manager() -> MCPSessionManager:
    """初始化全局 MCP 会话管理器
    
    在 aichat 模块初始化时调用。
    
    Returns:
        MCPSessionManager 实例
    """
    global mcp_session_manager
    if mcp_session_manager is None:
        mcp_session_manager = MCPSessionManager(mcp_server_manager)
        mcp_tool_bridge.set_session_manager(mcp_session_manager)
    return mcp_session_manager


__all__ = [
    # 配置
    "MCPServerConfig",
    # 客户端
    "MCPClient",
    # 管理器
    "MCPServerManager",
    "mcp_server_manager",
    # 会话管理器（渐进式加载）
    "MCPSessionManager",
    "mcp_session_manager",
    "init_mcp_session_manager",
    # 工具桥接
    "MCPToolBridge",
    "mcp_tool_bridge",
]
