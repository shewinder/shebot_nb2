"""MCP Server 管理器

管理多个 MCP server 的生命周期，包括启动、停止、发现工具等。
"""
from typing import Dict, List, Optional, Any
from loguru import logger

from .config import MCPServerConfig
from .client import MCPClient


class MCPServerManager:
    """MCP Server 管理器
    
    管理所有配置的 MCP server 实例，提供统一的访问接口。
    
    Example:
        from ..config import Config
        
        conf = Config.get_instance('aichat')
        manager = MCPServerManager()
        
        # 从配置加载 servers
        for server_config in conf.mcp_servers:
            if server_config.enabled:
                manager.add_server(server_config)
        
        # 启动所有 servers
        await manager.start_all()
        
        # 获取所有工具
        all_tools = manager.get_all_tools()
        
        # 调用特定 server 的工具
        result = await manager.call_tool("filesystem", "read_file", {"path": "/tmp/test.txt"})
    """
    
    def __init__(self):
        """初始化管理器"""
        self._clients: Dict[str, MCPClient] = {}
        self._configs: Dict[str, MCPServerConfig] = {}
    
    def add_server(self, config: MCPServerConfig) -> bool:
        """添加并初始化一个 MCP server
        
        Args:
            config: Server 配置
            
        Returns:
            是否添加成功
        """
        server_id = config.id
        
        if server_id in self._clients:
            logger.warning(f"MCP server {server_id} 已存在，将替换")
            # 先移除旧的
            self.remove_server(server_id)
        
        self._configs[server_id] = config
        client = MCPClient(config)
        self._clients[server_id] = client
        
        logger.debug(f"MCP server {server_id} 已添加到管理器")
        return True
    
    def remove_server(self, server_id: str) -> bool:
        """移除一个 MCP server
        
        Args:
            server_id: Server ID
            
        Returns:
            是否移除成功
        """
        if server_id not in self._clients:
            return False
        
        client = self._clients[server_id]
        
        # 异步断开需要特殊处理
        if client.is_connected:
            # 这里不能直接 await，需要由调用方确保先断开
            logger.warning(f"MCP server {server_id} 仍在连接状态，强制移除")
        
        del self._clients[server_id]
        del self._configs[server_id]
        
        logger.debug(f"MCP server {server_id} 已从管理器移除")
        return True
    
    async def start_server(self, server_id: str) -> bool:
        """启动单个 server
        
        Args:
            server_id: Server ID
            
        Returns:
            是否启动成功
        """
        if server_id not in self._clients:
            logger.error(f"MCP server {server_id} 不存在")
            return False
        
        client = self._clients[server_id]
        return await client.connect()
    
    async def stop_server(self, server_id: str) -> bool:
        """停止单个 server
        
        Args:
            server_id: Server ID
            
        Returns:
            是否停止成功
        """
        if server_id not in self._clients:
            return False
        
        client = self._clients[server_id]
        await client.disconnect()
        return True
    
    async def restart_server(self, server_id: str) -> bool:
        """重启单个 server
        
        Args:
            server_id: Server ID
            
        Returns:
            是否重启成功
        """
        await self.stop_server(server_id)
        return await self.start_server(server_id)
    
    async def start_all(self) -> Dict[str, bool]:
        """启动所有 server
        
        Returns:
            {server_id: 是否成功} 的字典
        """
        results = {}
        for server_id in self._clients:
            results[server_id] = await self.start_server(server_id)
        return results
    
    async def stop_all(self) -> None:
        """停止所有 server"""
        for server_id in self._clients:
            await self.stop_server(server_id)
    
    def get_server(self, server_id: str) -> Optional[MCPClient]:
        """获取指定 server 的客户端
        
        Args:
            server_id: Server ID
            
        Returns:
            MCPClient 实例，不存在返回 None
        """
        return self._clients.get(server_id)
    
    def list_servers(self) -> List[Dict[str, Any]]:
        """列出所有 server 状态
        
        Returns:
            Server 状态列表
        """
        result = []
        for server_id, client in self._clients.items():
            config = self._configs.get(server_id)
            result.append({
                "id": server_id,
                "name": client.name,
                "enabled": config.enabled if config else False,
                "connected": client.is_connected,
                "tool_count": len(client.tools),
                "transport": config.transport if config else "unknown"
            })
        return result
    
    def get_all_tools(self) -> List[Dict[str, Any]]:
        """获取所有 server 的所有工具
        
        Returns:
            工具列表，每个工具包含 server_id, name, description, inputSchema
        """
        all_tools = []
        for server_id, client in self._clients.items():
            if not client.is_connected:
                continue
            
            tools = client.tools
            for tool in tools:
                all_tools.append({
                    "server_id": server_id,
                    "server_name": client.name,
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {})
                })
        
        return all_tools
    
    async def call_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用指定 server 的工具
        
        Args:
            server_id: Server ID
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            调用结果
        """
        client = self.get_server(server_id)
        if not client:
            return {
                "content": [f"MCP server {server_id} 不存在"],
                "isError": True
            }
        
        if not client.is_connected:
            # 尝试连接
            if not await client.connect():
                return {
                    "content": [f"MCP server {server_id} 未连接"],
                    "isError": True
                }
        
        return await client.call_tool(tool_name, arguments)
    
    async def refresh_tools(self) -> None:
        """刷新所有 server 的工具列表"""
        for server_id, client in self._clients.items():
            if client.is_connected:
                try:
                    await client.list_tools()
                    logger.debug(f"MCP server {server_id} 工具列表已刷新")
                except Exception as e:
                    logger.exception(f"刷新 MCP server {server_id} 工具列表失败: {e}")


# 全局管理器实例
mcp_server_manager = MCPServerManager()
