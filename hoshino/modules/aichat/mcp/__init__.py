"""MCP (Model Context Protocol) 支持模块

为 aichat 提供 MCP 协议支持，允许连接外部 MCP servers 扩展 AI 能力。

Usage:
    from .mcp import mcp_server_manager, mcp_tool_bridge, MCPToolBridge
    
    # 配置并启动 MCP servers
    from ..config import Config
    conf = Config.get_instance('aichat')
    
    if conf.enable_mcp:
        for server_config in conf.mcp_servers:
            if server_config.enabled:
                mcp_server_manager.add_server(server_config)
        
        # 启动所有 servers
        await mcp_server_manager.start_all()
    
    # 获取 MCP 工具 schemas
    schemas = mcp_tool_bridge.get_tool_schemas()
    
    # 调用 MCP 工具
    result = await mcp_tool_bridge.call_mcp_tool("filesystem", "read_file", {"path": "/tmp/test.txt"})
"""

# 配置
from .config import MCPServerConfig

# 客户端
from .client import MCPClient

# 管理器
from .server_manager import MCPServerManager, mcp_server_manager

# 工具桥接
from .tool_bridge import MCPToolBridge, mcp_tool_bridge

__all__ = [
    # 配置
    "MCPServerConfig",
    # 客户端
    "MCPClient",
    # 管理器
    "MCPServerManager",
    "mcp_server_manager",
    # 工具桥接
    "MCPToolBridge",
    "mcp_tool_bridge",
]
