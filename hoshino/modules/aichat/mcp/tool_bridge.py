"""MCP 工具桥接模块

将 MCP 工具转换为 aichat 现有工具系统的格式，实现无缝集成。
支持渐进式加载：只加载会话中已激活的 MCP server 的工具。
"""
from typing import Any, Callable, Dict, List, Optional, Set
from loguru import logger

from .server_manager import MCPServerManager, mcp_server_manager


class MCPToolBridge:
    """MCP 工具桥接器
    
    将 MCP tools 转换为 aichat 工具系统可用的格式。
    支持渐进式加载：可以只获取特定会话中已激活的 server 的工具。
    
    Example:
        from .server_manager import mcp_server_manager
        from .session_manager import MCPSessionManager
        
        session_manager = MCPSessionManager(mcp_server_manager)
        bridge = MCPToolBridge(mcp_server_manager, session_manager)
        
        # 获取元数据摘要（用于 AI 选择）
        summary = bridge.get_metadata_summary()
        
        # 获取特定会话的激活工具
        schemas = await bridge.get_active_tool_schemas(session_id)
        
        # 调用 MCP 工具
        result = await bridge.call_mcp_tool("filesystem", "read_file", {"path": "/tmp/test.txt"})
    """
    
    def __init__(self, server_manager: MCPServerManager, session_manager: Optional[Any] = None):
        """初始化桥接器
        
        Args:
            server_manager: MCP server 管理器实例
            session_manager: MCP 会话管理器实例（可选，用于渐进式加载）
        """
        self.server_manager = server_manager
        self.session_manager = session_manager
        self._tool_cache: Dict[str, Dict[str, Any]] = {}  # {tool_key: tool_info}
    
    def set_session_manager(self, session_manager: Any) -> None:
        """设置会话管理器
        
        Args:
            session_manager: MCP 会话管理器实例
        """
        self.session_manager = session_manager
    
    def _make_tool_key(self, server_id: str, tool_name: str) -> str:
        """生成工具的唯一标识 key
        
        Args:
            server_id: Server ID
            tool_name: 工具名称
            
        Returns:
            唯一 key，格式: mcp_{server_id}_{tool_name}
        """
        # 处理可能的冲突：替换工具名中的特殊字符
        safe_name = tool_name.replace("-", "_").replace(".", "_")
        return f"mcp_{server_id}_{safe_name}"
    
    def _parse_tool_key(self, tool_key: str) -> Optional[tuple]:
        """从 tool_key 解析 server_id 和 tool_name
        
        Args:
            tool_key: 工具 key
            
        Returns:
            (server_id, tool_name) 或 None
        """
        if not tool_key.startswith("mcp_"):
            return None
        
        # 优先从缓存查询（避免 server_id 含下划线时切分错误）
        if tool_key in self._tool_cache:
            info = self._tool_cache[tool_key]
            return info["server_id"], info["tool_name"]
        
        # 降级：尝试切分（server_id 不含下划线时可正常工作）
        parts = tool_key[4:].split("_", 1)  # 去掉 "mcp_" 前缀
        if len(parts) != 2:
            return None
        
        return parts[0], parts[1]
    
    def convert_mcp_tool(self, server_id: str, server_name: str, tool: Dict[str, Any]) -> Dict[str, Any]:
        """将单个 MCP tool 转换为 OpenAI function calling 格式
        
        Args:
            server_id: Server ID
            server_name: Server 显示名称
            tool: MCP tool 定义
            
        Returns:
            OpenAI tools 格式的字典
        """
        tool_name = tool.get("name", "")
        description = tool.get("description", "")
        input_schema = tool.get("inputSchema", {})
        
        # 生成唯一 key
        tool_key = self._make_tool_key(server_id, tool_name)
        
        # 缓存工具信息
        self._tool_cache[tool_key] = {
            "server_id": server_id,
            "tool_name": tool_name,
            "server_name": server_name
        }
        
        # 构建 schema
        # 在描述中添加 server 信息，帮助 AI 理解
        enhanced_description = f"[{server_name}] {description}"
        
        return {
            "type": "function",
            "function": {
                "name": tool_key,
                "description": enhanced_description,
                "parameters": input_schema
            }
        }
    
    # ========== 渐进式加载新方法 ==========
    
    def get_metadata_summary(self) -> str:
        """获取 MCP server 元数据摘要（用于 AI 选择）
        
        返回一个格式化的文本，列出所有可用的 MCP server，
        供 AI 根据用户意图选择激活。
        
        Returns:
            格式化文本，如果没有可用的 server 返回空字符串
        """
        servers = self.server_manager.list_server_metadata()
        
        # 过滤出 AI 可自动触发的 server
        auto_servers = [s for s in servers if s.get("auto_trigger", True) and s.get("enabled", True)]
        
        if not auto_servers:
            return ""
        
        lines = [
            "=" * 40,
            "【MCP 系统】",
            "=" * 40,
            "",
            "📋 可用 MCP Server 列表（AI 可根据用户意图自动激活）：",
        ]
        
        for server in auto_servers:
            desc = server.get("description") or server.get("name", server["id"])
            lines.append(f"• {server['id']}: {desc}")
        
        lines.extend([
            "",
            "💡 使用指导：",
            "1. 当用户需求与某个 MCP server 功能匹配时，使用 activate_mcp_server 工具激活它",
            "2. 激活后，返回结果会告诉你具体的 MCP 工具名称（格式：mcp_<server_id>_<工具名>）",
            "3. 使用 MCP 工具时，直接调用 mcp_<server_id>_<工具名>，不要调用 execute_script！",
            "4. 如果当前没有合适的 MCP server，按常规方式回答",
            "5. 不要重复激活已激活的 MCP server",
            "",
            "🔧 使用方法：",
            "  - 激活：activate_mcp_server(server_id=\"xxx\")",
            "  - 调用 MCP 工具：mcp_xxx_toolname(args)",
            "",
            "⚠️ 注意：MCP 工具名称格式为 mcp_<server_id>_<原始工具名>，",
            "   激活后请查看返回结果中的具体工具名称！",
        ])
        
        return "\n".join(lines)
    
    async def get_active_tool_schemas(self, session_id: str) -> List[Dict[str, Any]]:
        """获取指定会话中已激活的 MCP 工具 schemas
        
        只返回会话中已激活的 server 的工具。
        
        Args:
            session_id: 会话 ID
            
        Returns:
            OpenAI tools 格式的列表
        """
        if not self.session_manager:
            logger.warning("MCPToolBridge: session_manager 未设置，无法获取激活的工具")
            return []
        
        active_servers = self.session_manager.get_active_servers(session_id)
        if not active_servers:
            return []
        
        tools = await self.server_manager.get_tools_for_servers(active_servers)
        
        schemas = []
        for tool in tools:
            schema = self.convert_mcp_tool(
                tool["server_id"],
                tool["server_name"],
                tool
            )
            schemas.append(schema)
        
        logger.debug(f"Session {session_id} 获取 {len(schemas)} 个 MCP 工具 schemas")
        return schemas
    
    def get_active_servers_summary(self, session_id: str) -> str:
        """获取已激活 server 的摘要
        
        Args:
            session_id: 会话 ID
            
        Returns:
            摘要文本
        """
        if not self.session_manager:
            return "MCP 会话管理器未初始化"
        
        return self.session_manager.get_active_servers_summary(session_id)
    
    # ========== 传统方法（向后兼容） ==========
    
    async def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """获取所有 MCP 工具的 schemas（用于传给 AI）
        
        注意：此方法会连接所有 server，获取所有工具。
        在渐进式加载模式下，建议使用 get_active_tool_schemas。
        
        Returns:
            OpenAI tools 格式的列表
        """
        schemas = []
        tools = await self.server_manager.get_all_tools()
        
        for tool in tools:
            schema = self.convert_mcp_tool(
                tool["server_id"],
                tool["server_name"],
                tool
            )
            schemas.append(schema)
        
        return schemas
    
    def get_tool_function(self, tool_key: str) -> Optional[Callable]:
        """获取工具的调用函数
        
        返回一个包装函数，实际调用时会路由到对应的 MCP server。
        
        Args:
            tool_key: 工具 key (格式: mcp_{server_id}_{tool_name})
            
        Returns:
            可调用函数，或 None
        """
        parsed = self._parse_tool_key(tool_key)
        if not parsed:
            return None
        
        server_id, tool_name = parsed
        
        # 返回包装函数
        async def tool_wrapper(**kwargs):
            return await self.call_mcp_tool_by_key(tool_key, kwargs)
        
        return tool_wrapper
    
    async def call_mcp_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用指定 MCP server 的工具
        
        将 MCP 工具返回结果转换为 aichat 工具系统格式。
        
        Args:
            server_id: Server ID
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            ToolResult 格式的结果
        """
        try:
            result = await self.server_manager.call_tool(server_id, tool_name, arguments)
            
            # 转换 MCP 结果为 ToolResult 格式
            content_parts = result.get("content", [])
            is_error = result.get("isError", False)
            
            # 拼接 content（content 是列表，可能包含文本、图片等）
            text_content = []
            image_urls = []
            
            for part in content_parts:
                if isinstance(part, str):
                    text_content.append(part)
                elif hasattr(part, 'text'):
                    # MCP TextContent 对象
                    text_content.append(part.text)
                elif hasattr(part, 'data') and hasattr(part, 'mimeType'):
                    # MCP ImageContent 对象
                    mime_type = part.mimeType
                    data = part.data
                    if mime_type.startswith("image/"):
                        image_url = f"data:{mime_type};base64,{data}"
                        image_urls.append(image_url)
                elif isinstance(part, dict):
                    if part.get('type') == 'text':
                        text_content.append(part.get('text', ''))
                    elif part.get('type') == 'image':
                        data = part.get('data', '')
                        mime = part.get('mimeType', 'image/png')
                        image_urls.append(f"data:{mime};base64,{data}")
            
            content = "\n".join(text_content) if text_content else ""
            
            return {
                "success": not is_error,
                "content": content,
                "images": image_urls,
                "error": content if is_error else None,
                "metadata": {
                    "server_id": server_id,
                    "tool_name": tool_name
                }
            }
            
        except Exception as e:
            logger.exception(f"调用 MCP 工具 {server_id}/{tool_name} 失败: {e}")
            return {
                "success": False,
                "content": f"工具调用失败: {str(e)}",
                "images": [],
                "error": str(e),
                "metadata": {}
            }
    
    async def call_mcp_tool_by_key(self, tool_key: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """通过 tool_key 调用 MCP 工具
        
        Args:
            tool_key: 工具 key (格式: mcp_{server_id}_{tool_name})
            arguments: 工具参数
            
        Returns:
            ToolResult 格式的结果
        """
        parsed = self._parse_tool_key(tool_key)
        if not parsed:
            return {
                "success": False,
                "content": f"无效的工具 key: {tool_key}",
                "images": [],
                "error": "无效的工具 key",
                "metadata": {}
            }
        
        server_id, tool_name = parsed
        return await self.call_mcp_tool(server_id, tool_name, arguments)
    
    def clear_cache(self) -> None:
        """清除工具缓存"""
        self._tool_cache.clear()


# 全局桥接器实例
mcp_tool_bridge = MCPToolBridge(mcp_server_manager)
