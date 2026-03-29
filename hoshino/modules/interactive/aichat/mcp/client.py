"""MCP 客户端封装

提供对 MCP server 的连接管理和工具调用功能。
当前仅支持 stdio 传输方式。
"""
import asyncio
import os
from typing import Any, Dict, List, Optional
from loguru import logger

# MCP SDK 导入
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import MCPServerConfig


class MCPClient:
    """MCP 客户端
    
    封装单个 MCP server 的连接和调用。
    
    Example:
        config = MCPServerConfig(
            id="filesystem",
            name="文件系统",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        )
        client = MCPClient(config)
        await client.connect()
        tools = await client.list_tools()
        result = await client.call_tool("read_file", {"path": "/tmp/test.txt"})
        await client.disconnect()
    """
    
    def __init__(self, config: MCPServerConfig):
        """初始化 MCP 客户端
        
        Args:
            config: MCP server 配置
        """
        self.config = config
        self.id = config.id
        self.name = config.name
        
        # stdio 相关
        self._session: Optional[Any] = None
        self._client_ctx = None
        self._session_ctx = None
        self._read_stream = None
        self._write_stream = None
        
        # 状态
        self._connected = False
        self._tools: List[Dict[str, Any]] = []
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected and self._session is not None
    
    @property
    def tools(self) -> List[Dict[str, Any]]:
        """获取已发现的工具列表"""
        return self._tools.copy()
    
    async def connect(self) -> bool:
        """连接到 MCP server
        
        Returns:
            是否连接成功
        """
        if self.is_connected:
            logger.debug(f"MCP client {self.id} 已连接")
            return True
        
        if self.config.transport != "stdio":
            logger.error(f"不支持的传输方式: {self.config.transport}")
            return False
        
        if not self.config.command:
            logger.error(f"MCP server {self.id} 未配置 command")
            return False
        
        try:
            logger.info(f"正在连接 MCP server: {self.id} ({self.name})")
            
            # 准备环境变量
            env = os.environ.copy()
            env.update(self.config.env)
            
            # 创建 server 参数
            server_params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args,
                env=env
            )
            
            # 创建 stdio 客户端
            self._client_ctx = stdio_client(server_params)
            self._read_stream, self._write_stream = await self._client_ctx.__aenter__()
            
            # 创建会话
            self._session_ctx = ClientSession(self._read_stream, self._write_stream)
            self._session = await self._session_ctx.__aenter__()
            
            # 初始化
            await self._session.initialize()
            
            self._connected = True
            logger.info(f"MCP server {self.id} 连接成功")
            
            # 立即发现工具
            await self._discover_tools()
            
            return True
            
        except Exception as e:
            logger.exception(f"连接 MCP server {self.id} 失败: {e}")
            await self._cleanup()
            return False
    
    async def disconnect(self) -> None:
        """断开连接"""
        await self._cleanup()
        logger.info(f"MCP server {self.id} 已断开")
    
    async def _cleanup(self) -> None:
        """清理资源"""
        self._connected = False
        self._tools = []
        
        if self._session_ctx:
            try:
                await self._session_ctx.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"关闭 session 时出错: {e}")
            self._session_ctx = None
        
        if self._client_ctx:
            try:
                await self._client_ctx.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"关闭 client 时出错: {e}")
            self._client_ctx = None
        
        self._session = None
        self._read_stream = None
        self._write_stream = None
    
    async def _discover_tools(self) -> None:
        """发现并缓存工具列表"""
        if not self.is_connected:
            return
        
        try:
            tools_result = await self._session.list_tools()
            # tools_result 是一个对象，包含 tools 属性
            if hasattr(tools_result, 'tools'):
                raw_tools = tools_result.tools
            else:
                raw_tools = tools_result
            
            # 转换为标准字典格式
            self._tools = []
            for tool in raw_tools:
                if hasattr(tool, 'name'):
                    tool_dict = {
                        "name": tool.name,
                        "description": getattr(tool, 'description', ''),
                        "inputSchema": getattr(tool, 'inputSchema', {})
                    }
                    self._tools.append(tool_dict)
                elif isinstance(tool, dict):
                    self._tools.append(tool)
            
            logger.info(f"MCP server {self.id} 发现 {len(self._tools)} 个工具")
            
        except Exception as e:
            logger.exception(f"发现工具失败: {e}")
            self._tools = []
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """获取工具列表
        
        Returns:
            工具列表，每个工具包含 name, description, inputSchema
        """
        if not self.is_connected:
            logger.warning(f"MCP client {self.id} 未连接，尝试重新连接")
            if not await self.connect():
                return []
        
        # 如果缓存为空，重新发现
        if not self._tools:
            await self._discover_tools()
        
        return self._tools.copy()
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            调用结果，包含 content 和 isError
        """
        if not self.is_connected:
            return {
                "content": [f"MCP client {self.id} 未连接"],
                "isError": True
            }
        
        try:
            logger.debug(f"调用 MCP 工具: {self.id}/{tool_name}, args: {arguments}")
            
            result = await self._session.call_tool(tool_name, arguments)
            
            # 转换结果为标准格式
            return {
                "content": result.content if hasattr(result, 'content') else [str(result)],
                "isError": result.isError if hasattr(result, 'isError') else False
            }
            
        except Exception as e:
            logger.exception(f"调用 MCP 工具 {tool_name} 失败: {e}")
            return {
                "content": [f"工具调用失败: {str(e)}"],
                "isError": True
            }
