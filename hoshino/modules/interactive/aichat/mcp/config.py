"""MCP 配置模型

本模块定义 MCP (Model Context Protocol) 相关的配置数据结构。
"""
from typing import Dict, List, Optional
from pydantic import BaseModel


class MCPServerConfig(BaseModel):
    """MCP Server 配置
    
    用于配置一个 MCP server 的连接参数。
    
    Example:
        # stdio 模式
        MCPServerConfig(
            id="filesystem",
            name="文件系统",
            transport="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            enabled=True
        )
        
        # sse 模式
        MCPServerConfig(
            id="remote",
            name="远程服务",
            transport="sse",
            url="http://localhost:3001/sse",
            enabled=True
        )
    """
    id: str                           # 唯一标识（英文，不含空格）
    name: str                         # 显示名称（中文可读）
    transport: str = "stdio"          # 传输方式: stdio | sse | http
    command: Optional[str] = None     # stdio 模式：可执行文件路径
    args: List[str] = []              # stdio 模式：命令参数
    url: Optional[str] = None         # sse/http 模式：服务 URL
    env: Dict[str, str] = {}          # 环境变量
    enabled: bool = True              # 是否启用

    class Config:
        # 允许额外字段，兼容未来扩展
        extra = "ignore"
