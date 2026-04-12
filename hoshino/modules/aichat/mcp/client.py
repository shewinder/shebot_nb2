"""MCP 客户端封装

提供对 MCP server 的连接管理和工具调用功能。
支持 sse 和 http 传输方式（通过 Docker 部署）。
"""
import asyncio
from typing import Any, Dict, List, Optional
from loguru import logger

# MCP SDK 导入
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
import httpx

from .config import MCPServerConfig

# 默认超时配置
CONNECT_TIMEOUT = 30  # 连接超时（秒）
CLEANUP_TIMEOUT = 5   # 清理超时（秒）
TOOL_CALL_TIMEOUT = 180  # 工具调用超时（秒）


class MCPClient:
    """MCP 客户端
    
    封装单个 MCP server 的连接和调用。
    支持 SSE 和 HTTP (Streamable HTTP) 传输方式，用于连接 Docker 部署的 MCP 服务。
    
    Example:
        config = MCPServerConfig(
            id="playwright",
            name="浏览器自动化",
            transport="http",
            url="http://playwright-mcp:8931/mcp"
        )
        client = MCPClient(config)
        await client.connect()
        tools = await client.list_tools()
        result = await client.call_tool("browser_navigate", {"url": "https://example.com"})
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
        
        # 连接相关
        self._session: Optional[Any] = None
        self._client_ctx = None
        self._session_ctx = None
        self._read_stream = None
        self._write_stream = None
        self._get_session_id: Optional[Any] = None  # HTTP 模式使用
        
        # 状态
        self._connected = False
        self._tools: List[Dict[str, Any]] = []
        self._needs_rebuild = False  # 标记是否需要完全重建（client 实例损坏）
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected and self._session is not None
    
    @property
    def needs_rebuild(self) -> bool:
        """是否需要完全重建 client 实例"""
        return self._needs_rebuild
    
    @property
    def tools(self) -> List[Dict[str, Any]]:
        """获取已发现的工具列表"""
        return self._tools.copy()
    
    async def connect(self, timeout: Optional[int] = None) -> bool:
        """连接到 MCP server
        
        Args:
            timeout: 连接超时（秒），默认 CONNECT_TIMEOUT
        
        Returns:
            是否连接成功
        """
        if self.is_connected:
            logger.debug(f"MCP client {self.id} 已连接")
            return True
        
        # 连接前强制清理，避免残留状态
        await self._cleanup()
        
        timeout = timeout or CONNECT_TIMEOUT
        
        try:
            if self.config.transport == "sse":
                return await asyncio.wait_for(
                    self._connect_sse(),
                    timeout=timeout
                )
            elif self.config.transport == "http":
                return await asyncio.wait_for(
                    self._connect_http(),
                    timeout=timeout
                )
            else:
                logger.error(f"不支持的传输方式: {self.config.transport}，支持 sse/http")
                return False
        except asyncio.TimeoutError:
            logger.error(f"连接 MCP server {self.id} 超时（{timeout}秒）")
            await self._cleanup()
            return False
        except Exception as e:
            logger.exception(f"连接 MCP server {self.id} 失败: {e}")
            await self._cleanup()
            return False
    
    async def _connect_sse(self) -> bool:
        """通过 SSE 方式连接"""
        if not self.config.url:
            logger.error(f"MCP server {self.id} 未配置 url")
            return False
        
        try:
            logger.info(f"正在通过 SSE 连接 MCP server: {self.id} ({self.name})")
            logger.info(f"SSE URL: {self.config.url}")
            
            # 创建 SSE 客户端
            self._client_ctx = sse_client(self.config.url, headers=self.config.headers)
            self._read_stream, self._write_stream = await self._client_ctx.__aenter__()
            
            # 创建会话
            self._session_ctx = ClientSession(self._read_stream, self._write_stream)
            self._session = await self._session_ctx.__aenter__()
            
            # 初始化
            await self._session.initialize()
            
            self._connected = True
            logger.info(f"MCP server {self.id} (SSE) 连接成功")
            
            # 立即发现工具
            await self._discover_tools()
            
            return True
            
        except Exception as e:
            logger.exception(f"连接 MCP server {self.id} (SSE) 失败: {e}")
            await self._cleanup()
            return False
    
    async def _connect_http(self) -> bool:
        """通过 HTTP (Streamable HTTP) 方式连接"""
        if not self.config.url:
            logger.error(f"MCP server {self.id} 未配置 url")
            return False
        
        try:
            logger.info(f"正在通过 HTTP 连接 MCP server: {self.id} ({self.name})")
            logger.info(f"HTTP URL: {self.config.url}")
            
            # 创建 HTTP 客户端
            # streamable_http_client 返回三元组: (read_stream, write_stream, get_session_id)
            # 使用自定义 headers 创建 httpx 客户端
            http_client = httpx.AsyncClient(headers=self.config.headers) if self.config.headers else None
            self._client_ctx = streamable_http_client(self.config.url, http_client=http_client)
            self._read_stream, self._write_stream, self._get_session_id = await self._client_ctx.__aenter__()
            
            # 创建会话
            self._session_ctx = ClientSession(self._read_stream, self._write_stream)
            self._session = await self._session_ctx.__aenter__()
            
            # 初始化
            await self._session.initialize()
            
            self._connected = True
            logger.info(f"MCP server {self.id} (HTTP) 连接成功")
            
            # 立即发现工具
            await self._discover_tools()
            
            return True
            
        except Exception as e:
            logger.exception(f"连接 MCP server {self.id} (HTTP) 失败: {e}")
            await self._cleanup()
            return False
    
    async def disconnect(self) -> None:
        """断开连接"""
        await self._cleanup()
        logger.info(f"MCP server {self.id} 已断开")
    
    async def _cleanup(self) -> None:
        """清理资源
        
        使用超时机制确保不会无限阻塞，防止 Ctrl+C 无法退出。
        """
        self._connected = False
        self._tools = []
        self._get_session_id = None
        
        async def _do_cleanup():
            """实际清理逻辑"""
            nonlocal self
            if self._session_ctx:
                try:
                    await self._session_ctx.__aexit__(None, None, None)
                except Exception as e:
                    logger.debug(f"关闭 session 时出错: {e}")
                finally:
                    self._session_ctx = None
            
            if self._client_ctx:
                try:
                    await self._client_ctx.__aexit__(None, None, None)
                except Exception as e:
                    logger.debug(f"关闭 client 时出错: {e}")
                finally:
                    self._client_ctx = None
            
            self._session = None
            self._read_stream = None
            self._write_stream = None
        
        try:
            # 使用超时，防止清理操作阻塞
            await asyncio.wait_for(_do_cleanup(), timeout=CLEANUP_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f"清理 MCP client {self.id} 资源超时（{CLEANUP_TIMEOUT}秒），强制清理")
            # 强制重置所有引用，让 GC 回收
            self._session_ctx = None
            self._client_ctx = None
            self._session = None
            self._read_stream = None
            self._write_stream = None
        except RuntimeError as e:
            # 忽略 anyio CancelScope 相关错误（NoneBot2 已知问题）
            if "cancel scope" in str(e).lower():
                logger.debug(f"清理 MCP client {self.id} 时遇到 CancelScope 问题（可忽略）: {e}")
            else:
                logger.exception(f"清理 MCP client {self.id} 资源时出错: {e}")
            # 强制清理
            self._session_ctx = None
            self._client_ctx = None
            self._session = None
            self._read_stream = None
            self._write_stream = None
        except Exception as e:
            logger.exception(f"清理 MCP client {self.id} 资源时出错: {e}")
            # 同样强制清理
            self._session_ctx = None
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
        
        async def _do_call():
            """实际调用逻辑"""
            result = await self._session.call_tool(tool_name, arguments)
            return {
                "content": result.content if hasattr(result, 'content') else [str(result)],
                "isError": result.isError if hasattr(result, 'isError') else False
            }
        
        try:
            logger.debug(f"调用 MCP 工具: {self.id}/{tool_name}, args: {arguments}")
            
            # 使用超时，防止无限阻塞
            return await asyncio.wait_for(_do_call(), timeout=TOOL_CALL_TIMEOUT)
            
        except asyncio.TimeoutError:
            logger.error(f"调用 MCP 工具 {tool_name} 超时（{TOOL_CALL_TIMEOUT}秒）")
            # 标记需要重建，因为可能已经卡死
            self._needs_rebuild = True
            return {
                "content": [f"工具调用超时（{TOOL_CALL_TIMEOUT}秒），请重试"],
                "isError": True
            }
            
        except Exception as e:
            error_msg = str(e)
            # 检查是否是 session 已终止的错误，尝试重连一次
            error_lower = error_msg.lower()
            if "terminated" in error_lower or "session closed" in error_lower or "connection closed" in error_lower:
                logger.warning(f"MCP session {self.id} 已终止，尝试重连...")
                await self._cleanup()
                if await self.connect():
                    logger.info(f"MCP session {self.id} 重连成功，重新调用工具")
                    try:
                        result = await self._session.call_tool(tool_name, arguments)
                        return {
                            "content": result.content if hasattr(result, 'content') else [str(result)],
                            "isError": result.isError if hasattr(result, 'isError') else False
                        }
                    except Exception as e2:
                        logger.exception(f"重连后调用 MCP 工具 {tool_name} 仍失败: {e2}")
                        # 重连后仍失败，标记需要重建
                        self._needs_rebuild = True
                        return {
                            "content": [f"工具调用失败（重连后）: {str(e2)}"],
                            "isError": True
                        }
                else:
                    logger.error(f"MCP session {self.id} 重连失败，标记需要重建")
                    # 重连失败，标记需要重建
                    self._needs_rebuild = True
            
            logger.exception(f"调用 MCP 工具 {tool_name} 失败: {e}")
            return {
                "content": [f"工具调用失败: {error_msg}"],
                "isError": True
            }
