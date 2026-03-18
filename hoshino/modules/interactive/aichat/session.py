"""
Session 管理模块
管理用户对话的 Session，包括历史消息和过期检查
"""
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from .config import Config

# 加载配置
conf = Config.get_instance('aichat')


class Session:
    """对话Session"""
    def __init__(self, session_id: str, persona: Optional[str] = None):
        self.session_id = session_id
        self.messages: List[Dict[str, Any]] = []  # 对话历史（支持文本和多模态）
        self.last_active = time.time()  # 最后活跃时间
        self.continuous_mode = False  # 是否处于连续对话模式（免#触发）
        self.choice_mode_enabled = False  # 是否开启选项生成模式
        self.choice_guideline: Optional[str] = None  # 选项生成指导标准
        self.last_choices: Dict[int, str] = {}  # 上一次生成的选项 {1: "选项1", 2: "选项2", 3: "选项3"}
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
        # 记录用户的连续对话模式状态，独立于session生命周期
        self.continuous_users: Dict[str, bool] = {}
        # 记录用户的选项模式状态和设置
        self.choice_mode_users: Dict[str, bool] = {}  # session_id -> enabled
        self.choice_guideline_users: Dict[str, Optional[str]] = {}  # session_id -> guideline
    
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
                # 过期则删除（连续对话模式也自动退出）
                del self.sessions[session_id]
                if session_id in self.continuous_users:
                    del self.continuous_users[session_id]
        
        # 创建新session，应用人格
        session = Session(session_id, persona)
        # 恢复连续对话模式状态（如果之前设置了）
        if self.continuous_users.get(session_id, False):
            session.continuous_mode = True
        # 恢复选项模式状态（如果之前设置了）
        if self.choice_mode_users.get(session_id, False):
            session.choice_mode_enabled = True
            session.choice_guideline = self.choice_guideline_users.get(session_id, None)
        self.sessions[session_id] = session
        return session
    
    def clear_session(self, user_id: int, group_id: Optional[int] = None) -> bool:
        """清除session"""
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            del self.sessions[session_id]
            # 清除连续对话模式状态
            if session_id in self.continuous_users:
                del self.continuous_users[session_id]
            # 清除选项模式状态
            if session_id in self.choice_mode_users:
                del self.choice_mode_users[session_id]
            if session_id in self.choice_guideline_users:
                del self.choice_guideline_users[session_id]
            return True
        return False
    
    def set_continuous_mode(self, user_id: int, group_id: Optional[int] = None, enabled: bool = True) -> bool:
        """设置连续对话模式"""
        session_id = self.get_session_id(user_id, group_id)
        self.continuous_users[session_id] = enabled
        
        # 如果当前有活跃session，也更新其状态
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                session.continuous_mode = enabled
                return True
        return False
    
    def is_continuous_mode(self, user_id: int, group_id: Optional[int] = None) -> bool:
        """检查是否处于连续对话模式"""
        session_id = self.get_session_id(user_id, group_id)
        
        # 优先检查活跃session
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session.continuous_mode
        
        # 否则检查持久化的状态
        return self.continuous_users.get(session_id, False)
    
    def set_choice_mode(self, user_id: int, group_id: Optional[int] = None, enabled: bool = True, guideline: Optional[str] = None) -> bool:
        """设置选项生成模式"""
        session_id = self.get_session_id(user_id, group_id)
        self.choice_mode_users[session_id] = enabled
        if enabled and guideline:
            self.choice_guideline_users[session_id] = guideline
        elif not enabled:
            if session_id in self.choice_guideline_users:
                del self.choice_guideline_users[session_id]
        
        # 如果当前有活跃session，也更新其状态
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                session.choice_mode_enabled = enabled
                session.choice_guideline = guideline if enabled else None
                if not enabled:
                    session.last_choices = {}
                return True
        return False
    
    def get_choice_mode(self, user_id: int, group_id: Optional[int] = None) -> Tuple[bool, Optional[str]]:
        """获取选项生成模式状态和设置
        
        Returns:
            (enabled, guideline) 元组
        """
        session_id = self.get_session_id(user_id, group_id)
        
        # 优先检查活跃session
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session.choice_mode_enabled, session.choice_guideline
        
        # 否则检查持久化的状态
        enabled = self.choice_mode_users.get(session_id, False)
        guideline = self.choice_guideline_users.get(session_id, None)
        return enabled, guideline
    
    def set_last_choices(self, user_id: int, group_id: Optional[int] = None, choices: Dict[int, str] = None) -> bool:
        """存储上一次生成的选项"""
        session_id = self.get_session_id(user_id, group_id)
        
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                session.last_choices = choices or {}
                return True
        return False
    
    def get_last_choices(self, user_id: int, group_id: Optional[int] = None) -> Dict[int, str]:
        """获取上一次生成的选项"""
        session_id = self.get_session_id(user_id, group_id)
        
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session.last_choices
        return {}
    
    def rollback_messages(self, user_id: int, group_id: Optional[int] = None, count: int = 1) -> int:
        """回溯消息，删除最近的 N 条对话（用户+AI算一条）
        
        Args:
            count: 要删除的对话条数
            
        Returns:
            实际删除的消息数量
        """
        session_id = self.get_session_id(user_id, group_id)
        if session_id not in self.sessions:
            return 0
        
        session = self.sessions[session_id]
        if not session.messages:
            return 0
        
        # 保留 system message
        system_msg = None
        start_idx = 0
        if session.messages and session.messages[0].get("role") == "system":
            system_msg = session.messages[0]
            start_idx = 1
        
        # 计算要删除多少条消息（一条对话 = user + assistant = 2条消息）
        messages_to_delete = count * 2
        
        # 获取当前非系统消息列表
        other_messages = session.messages[start_idx:]
        
        # 如果消息数不足，只删除存在的
        if len(other_messages) <= messages_to_delete:
            deleted = len(other_messages)
            other_messages = []
        else:
            deleted = messages_to_delete
            other_messages = other_messages[:-messages_to_delete]
        
        # 重新组合
        if system_msg:
            session.messages = [system_msg] + other_messages
        else:
            session.messages = other_messages
        
        session.last_active = time.time()
        return deleted


# 全局Session管理器
session_manager = SessionManager()
