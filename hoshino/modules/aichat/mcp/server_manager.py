"""MCP Server 管理器

管理多个 MCP server 的生命周期，包括启动、停止、发现工具等。
支持渐进式加载：只保存配置，按需连接。
"""
from typing import Dict, List, Optional, Any, Set
from loguru import logger

from .config import MCPServerConfig
from .client import MCPClient


class MCPServerManager:
    """MCP Server 管理器
    
    管理所有配置的 MCP server 实例，提供统一的访问接口。
    支持渐进式加载：初始化时只保存配置，首次激活时才连接。
    
    Example:
        from ..config import Config
        
        conf = Config.get_instance('aichat')
        manager = MCPServerManager()
        
        # 方式1: 渐进式加载（推荐）
        manager.initialize(conf.mcp_servers)
        # 按需连接
        await manager.ensure_connected("playwright")
        
        # 方式2: 传统方式（兼容旧代码）
        for server_config in conf.mcp_servers:
            if server_config.enabled:
                manager.add_server(server_config)
        await manager.start_all()
        
        # 获取工具
        all_tools = manager.get_all_tools()
        
        # 调用特定 server 的工具
        result = await manager.call_tool("filesystem", "read_file", {"path": "/tmp/test.txt"})
    """
    
    def __init__(self):
        """初始化管理器"""
        self._clients: Dict[str, MCPClient] = {}
        self._configs: Dict[str, MCPServerConfig] = {}
        self._initialized = False
    
    # ========== 渐进式加载新方法 ==========
    
    def initialize(self, configs: List[MCPServerConfig]) -> None:
        """初始化管理器（渐进式加载）
        
        只保存配置，不立即创建 client 或连接。
        在首次 ensure_connected 时才实际连接。
        
        Args:
            configs: MCP server 配置列表
        """
        if self._initialized:
            return
        
        for config in configs:
            if config.enabled:
                self._configs[config.id] = config
                # 注意：这里不创建 client，延迟到 ensure_connected 时
        
        self._initialized = True
        logger.info(f"MCPServerManager 初始化完成，共 {len(self._configs)} 个配置")
    
    def get_server_config(self, server_id: str) -> Optional[MCPServerConfig]:
        """获取 server 配置
        
        Args:
            server_id: Server ID
            
        Returns:
            MCPServerConfig 或 None
        """
        return self._configs.get(server_id)
    
    def list_server_metadata(self) -> List[Dict[str, Any]]:
        """列出所有 server 的元数据（无需连接）
        
        Returns:
            Server 元数据列表，包含 id, name, description, auto_trigger, enabled
        """
        result = []
        for server_id, config in self._configs.items():
            result.append({
                "id": server_id,
                "name": config.name,
                "description": config.description,
                "enabled": config.enabled,
                "auto_trigger": config.auto_trigger,
                "keywords": config.keywords,
                "connected": server_id in self._clients and self._clients[server_id].is_connected
            })
        return result
    
    async def ensure_connected(self, server_id: str) -> bool:
        """确保指定 server 已连接（延迟连接）
        
        如果 client 不存在，会创建并连接。
        如果 client 已存在但未连接，会尝试连接。
        
        Args:
            server_id: Server ID
            
        Returns:
            是否已连接
        """
        # 检查配置是否存在
        if server_id not in self._configs:
            logger.error(f"MCP server {server_id} 未配置")
            return False
        
        # 已存在 client 且已连接
        if server_id in self._clients:
            client = self._clients[server_id]
            if client.is_connected:
                return True
            # 需要重连
            logger.debug(f"MCP client {server_id} 未连接，尝试重连...")
            return await client.connect()
        
        # 创建新 client 并连接
        config = self._configs[server_id]
        client = MCPClient(config)
        self._clients[server_id] = client
        
        logger.info(f"正在连接 MCP server: {server_id} ({config.name})")
        return await client.connect()
    
    async def get_tools_for_servers(self, server_ids: Set[str]) -> List[Dict[str, Any]]:
        """获取指定 servers 的工具列表
        
        只查询已激活（传入的）servers，实现渐进式加载。
        
        Args:
            server_ids: Server ID 集合
            
        Returns:
            工具列表，每个工具包含 server_id, server_name, name, description, inputSchema
        """
        all_tools = []
        for server_id in server_ids:
            # 确保已连接
            if not await self.ensure_connected(server_id):
                logger.warning(f"MCP server {server_id} 连接失败，跳过工具列表")
                continue
            
            client = self._clients[server_id]
            config = self._configs.get(server_id)
            
            tools = client.tools
            for tool in tools:
                all_tools.append({
                    "server_id": server_id,
                    "server_name": config.name if config else server_id,
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {})
                })
        
        return all_tools
    
    # ========== 传统方法（向后兼容） ==========
    
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
        if server_id not in self._configs:
            return False
        
        # 如果存在 client，断开并移除
        if server_id in self._clients:
            client = self._clients[server_id]
            if client.is_connected:
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
        return await self.ensure_connected(server_id)
    
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
        for server_id in self._configs:
            results[server_id] = await self.ensure_connected(server_id)
        return results
    
    async def stop_all(self) -> None:
        """停止所有 server"""
        for server_id in list(self._clients.keys()):
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
        for server_id, config in self._configs.items():
            client = self._clients.get(server_id)
            result.append({
                "id": server_id,
                "name": config.name,
                "enabled": config.enabled,
                "connected": client.is_connected if client else False,
                "tool_count": len(client.tools) if client else 0,
                "transport": config.transport,
                "description": config.description,
                "auto_trigger": config.auto_trigger
            })
        return result
    
    async def get_all_tools(self) -> List[Dict[str, Any]]:
        """获取所有 server 的所有工具
        
        自动尝试重连未连接的 client，确保工具列表始终可用。
        
        Returns:
            工具列表，每个工具包含 server_id, name, description, inputSchema
        """
        all_tools = []
        for server_id in list(self._configs.keys()):
            if not await self.ensure_connected(server_id):
                continue
            
            client = self._clients[server_id]
            config = self._configs.get(server_id)
            
            # 如果 client 需要重建，直接重建
            if client.needs_rebuild:
                logger.warning(f"MCP client {server_id} 需要重建，正在重建...")
                if not await self._recreate_client(server_id):
                    continue
                client = self._clients[server_id]
            
            tools = client.tools
            for tool in tools:
                all_tools.append({
                    "server_id": server_id,
                    "server_name": config.name if config else server_id,
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {})
                })
        
        return all_tools
    
    async def _recreate_client(self, server_id: str) -> bool:
        """重新创建 client 实例
        
        当 client 损坏（needs_rebuild=True）时，完全重建。
        
        Args:
            server_id: Server ID
            
        Returns:
            是否重建成功
        """
        if server_id not in self._configs:
            return False
        
        config = self._configs.get(server_id)
        if not config:
            logger.error(f"无法重建 MCP client {server_id}：配置不存在")
            return False
        
        # 停止旧 client（如果存在）
        if server_id in self._clients:
            old_client = self._clients[server_id]
            try:
                await old_client.disconnect()
            except Exception as e:
                logger.debug(f"断开旧 MCP client {server_id} 时出错: {e}")
        
        # 创建新 client
        try:
            new_client = MCPClient(config)
            self._clients[server_id] = new_client
            
            # 尝试连接
            if await new_client.connect():
                logger.info(f"MCP client {server_id} 重建并连接成功")
                return True
            else:
                logger.error(f"MCP client {server_id} 重建后连接失败")
                return False
        except Exception as e:
            logger.exception(f"重建 MCP client {server_id} 失败: {e}")
            return False
    
    async def call_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用指定 server 的工具
        
        支持自动重连和 client 重建。
        
        Args:
            server_id: Server ID
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            调用结果
        """
        # 确保已连接
        if not await self.ensure_connected(server_id):
            return {
                "content": [f"MCP server {server_id} 连接失败"],
                "isError": True
            }
        
        client = self._clients[server_id]
        
        # 如果 client 需要重建，先重建
        if client.needs_rebuild:
            logger.warning(f"MCP client {server_id} 需要重建，正在重建...")
            if not await self._recreate_client(server_id):
                return {
                    "content": [f"MCP server {server_id} 重建失败"],
                    "isError": True
                }
            client = self._clients[server_id]
        
        # 调用工具
        result = await client.call_tool(tool_name, arguments)
        
        # 如果调用后 client 标记需要重建，下次调用会触发重建
        if client.needs_rebuild:
            logger.warning(f"MCP client {server_id} 调用后标记需要重建，将在下次使用时重建")
        
        return result
    
    async def refresh_tools(self) -> None:
        """刷新所有已连接 server 的工具列表"""
        for server_id, client in self._clients.items():
            if client.is_connected:
                try:
                    await client.list_tools()
                    logger.debug(f"MCP server {server_id} 工具列表已刷新")
                except Exception as e:
                    logger.exception(f"刷新 MCP server {server_id} 工具列表失败: {e}")


# 全局管理器实例
mcp_server_manager = MCPServerManager()
