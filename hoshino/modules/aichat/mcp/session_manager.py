"""
Author: SheBot
Date: 2026-04-12
Description: MCP 会话管理器 - 管理会话级 MCP server 激活状态
"""
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Tuple

from loguru import logger


@dataclass
class SessionMCPState:
    """会话级 MCP 状态"""
    active_servers: Set[str] = field(default_factory=set)  # 已激活的 server ID 集合
    activation_time: Dict[str, float] = field(default_factory=dict)  # 激活时间


class MCPSessionManager:
    """MCP 会话管理器
    
    管理会话级别的 MCP server 激活状态，实现渐进式加载。
    每个会话可以独立激活不同的 MCP server，互不干扰。
    
    Example:
        from .server_manager import mcp_server_manager
        
        session_manager = MCPSessionManager(mcp_server_manager)
        
        # 激活 server
        success, message = await session_manager.activate_server(session_id, "playwright")
        
        # 获取已激活的 servers
        active = session_manager.get_active_servers(session_id)
        
        # 清理会话
        session_manager.clear_session(session_id)
    """
    
    # 单个会话最大激活 server 数量
    MAX_SERVERS_PER_SESSION = 3
    
    def __init__(self, server_manager):
        """初始化
        
        Args:
            server_manager: MCPServerManager 实例
        """
        self.server_manager = server_manager
        # 会话状态: session_id -> SessionMCPState
        self._session_states: Dict[str, SessionMCPState] = {}
    
    def _get_session_state(self, session_id: str) -> SessionMCPState:
        """获取或创建会话状态"""
        if session_id not in self._session_states:
            self._session_states[session_id] = SessionMCPState()
        return self._session_states[session_id]
    
    async def activate_server(self, session_id: str, server_id: str) -> Tuple[bool, str]:
        """激活指定 MCP server
        
        Args:
            session_id: 会话 ID
            server_id: MCP server ID
            
        Returns:
            Tuple[success: bool, message: str]
        """
        # 检查 server 是否存在
        config = self.server_manager.get_server_config(server_id)
        if not config:
            return False, f"MCP server '{server_id}' 不存在"
        
        # 检查是否启用
        if not config.enabled:
            return False, f"MCP server '{server_id}' 已禁用"
        
        state = self._get_session_state(session_id)
        
        # 检查是否已激活
        if server_id in state.active_servers:
            return True, f"MCP server '{server_id}' 已经激活"
        
        # 检查数量限制
        if len(state.active_servers) >= self.MAX_SERVERS_PER_SESSION:
            return False, f"单个会话最多激活 {self.MAX_SERVERS_PER_SESSION} 个 MCP server"
        
        # 延迟连接：确保 server 已连接
        if not await self.server_manager.ensure_connected(server_id):
            return False, f"MCP server '{server_id}' 连接失败"
        
        # 激活
        state.active_servers.add(server_id)
        state.activation_time[server_id] = time.time()
        
        logger.info(f"Session {session_id} 激活 MCP server: {server_id}")
        return True, f"MCP server '{server_id}' 已激活"
    
    def deactivate_server(self, session_id: str, server_id: str) -> bool:
        """停用指定 MCP server
        
        Args:
            session_id: 会话 ID
            server_id: MCP server ID
            
        Returns:
            是否成功停用
        """
        state = self._get_session_state(session_id)
        
        if server_id not in state.active_servers:
            return False
        
        state.active_servers.discard(server_id)
        state.activation_time.pop(server_id, None)
        
        logger.info(f"Session {session_id} 停用 MCP server: {server_id}")
        return True
    
    def get_active_servers(self, session_id: str) -> Set[str]:
        """获取会话中已激活的 server ID 集合
        
        Args:
            session_id: 会话 ID
            
        Returns:
            已激活的 server ID 集合
        """
        state = self._session_states.get(session_id)
        if not state:
            return set()
        return state.active_servers.copy()
    
    def is_server_active(self, session_id: str, server_id: str) -> bool:
        """检查指定 server 是否已激活
        
        Args:
            session_id: 会话 ID
            server_id: MCP server ID
            
        Returns:
            是否已激活
        """
        state = self._session_states.get(session_id)
        if not state:
            return False
        return server_id in state.active_servers
    
    def get_active_servers_summary(self, session_id: str) -> str:
        """获取已激活 server 的摘要（用于用户查询）
        
        Args:
            session_id: 会话 ID
            
        Returns:
            摘要文本
        """
        active = self.get_active_servers(session_id)
        if not active:
            return "当前没有激活的 MCP server"
        
        lines = [f"当前已激活 {len(active)} 个 MCP server："]
        for server_id in active:
            config = self.server_manager.get_server_config(server_id)
            if config:
                lines.append(f"• {server_id}: {config.description or config.name}")
            else:
                lines.append(f"• {server_id}")
        
        return "\n".join(lines)
    
    def clear_session(self, session_id: str) -> None:
        """清理会话状态
        
        在会话结束时调用，释放相关资源。
        
        Args:
            session_id: 会话 ID
        """
        if session_id in self._session_states:
            del self._session_states[session_id]
            logger.debug(f"清理会话 MCP 状态: {session_id}")
    
    def get_all_session_stats(self) -> Dict[str, dict]:
        """获取所有会话的统计信息（用于调试）
        
        Returns:
            统计信息字典
        """
        stats = {}
        for session_id, state in self._session_states.items():
            stats[session_id] = {
                "active_servers": list(state.active_servers),
                "activation_time": state.activation_time
            }
        return stats
