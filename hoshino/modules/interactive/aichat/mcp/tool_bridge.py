"""MCP 工具桥接模块

将 MCP 工具转换为 aichat 现有工具系统的格式，实现无缝集成。
"""
from typing import Any, Callable, Dict, List, Optional
from loguru import logger

from .server_manager import MCPServerManager, mcp_server_manager


class MCPToolBridge:
    """MCP 工具桥接器
    
    将 MCP tools 转换为 aichat 工具系统可用的格式。
    
    Example:
        bridge = MCPToolBridge(mcp_server_manager)
        
        # 获取转换后的工具 schemas
        schemas = bridge.get_tool_schemas()
        
        # 获取工具函数映射
        functions = bridge.get_tool_functions()
        
        # 调用 MCP 工具
        result = await bridge.call_mcp_tool("filesystem", "read_file", {"path": "/tmp/test.txt"})
    """
    
    def __init__(self, server_manager: MCPServerManager):
        """初始化桥接器
        
        Args:
            server_manager: MCP server 管理器实例
        """
        self.server_manager = server_manager
        self._tool_cache: Dict[str, Dict[str, Any]] = {}  # {tool_key: tool_info}
    
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
    
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """获取所有 MCP 工具的 schemas（用于传给 AI）
        
        Returns:
            OpenAI tools 格式的列表
        """
        schemas = []
        tools = self.server_manager.get_all_tools()
        
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
