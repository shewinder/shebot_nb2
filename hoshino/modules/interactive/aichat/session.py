"""
Session 管理模块
管理用户对话的 Session，包括历史消息和过期检查
"""
import time
from typing import Any, Dict, List, Optional, Union

from .config import Config

# 加载配置
conf = Config.get_instance('aichat')


class Session:
    """对话Session"""
    def __init__(self, session_id: str, persona: Optional[str] = None):
        self.session_id = session_id
        self.messages: List[Dict[str, Any]] = []  # 对话历史（支持文本和多模态）
        self.last_active = time.time()  # 最后活跃时间
        # 如果有人格，在初始化时添加system message
        if persona:
            self.messages.append({"role": "system", "content": persona})
    
    def add_message(self, role: str, content: Union[str, List[Dict[str, Any]]]):
        """添加消息到历史（支持文本或多模态内容）"""
        self.messages.append({"role": role, "content": content})
        # 限制历史消息数量（保留system message）
        system_msg = None
        if self.messages and self.messages[0].get("role") == "system":
            system_msg = self.messages[0]
            other_messages = self.messages[1:]
        else:
            other_messages = self.messages
        
        if len(other_messages) > conf.max_history * 2:  # *2因为包含user和assistant
            other_messages = other_messages[-conf.max_history * 2:]
        
        if system_msg:
            self.messages = [system_msg] + other_messages
        else:
            self.messages = other_messages
        
        self.last_active = time.time()
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if conf.session_timeout <= 0:
            return False
        return time.time() - self.last_active > conf.session_timeout


class SessionManager:
    """管理所有Session（仅内存，不持久化）"""
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
    
    def get_session_id(self, user_id: int, group_id: Optional[int] = None) -> str:
        """获取session ID"""
        if group_id:
            return f"group_{group_id}_user_{user_id}"
        return f"private_{user_id}"
    
    def get_session(self, user_id: int, group_id: Optional[int] = None, persona: Optional[str] = None) -> Session:
        """获取或创建session"""
        session_id = self.get_session_id(user_id, group_id)
        
        # 检查是否存在且未过期
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session
            else:
                # 过期则删除
                del self.sessions[session_id]
        
        # 创建新session，应用人格
        session = Session(session_id, persona)
        self.sessions[session_id] = session
        return session
    
    def clear_session(self, user_id: int, group_id: Optional[int] = None) -> bool:
        """清除session"""
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False


# 全局Session管理器
session_manager = SessionManager()
