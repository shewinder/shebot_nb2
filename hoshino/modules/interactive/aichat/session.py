"""Session 管理模块"""
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from .config import Config

conf = Config.get_instance('aichat')


class Session:
    def __init__(self, session_id: str, persona: Optional[str] = None):
        self.session_id = session_id
        self.messages: List[Dict[str, Any]] = []
        self.last_active = time.time()
        self.continuous_mode = False
        self.choice_mode_enabled = False
        self.choice_guideline: Optional[str] = None
        self.last_choices: Dict[int, str] = {}
        self._user_images: Dict[str, str] = {}
        self._ai_images: Dict[str, str] = {}
        if persona:
            self.messages.append({"role": "system", "content": persona})
    
    def add_message(self, role: str, content: Union[str, List[Dict[str, Any]]]):
        self.messages.append({"role": role, "content": content})
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
    
    def store_user_image(self, image_data: str) -> str:
        identifier = f"<user_image_{len(self._user_images) + 1}>"
        self._user_images[identifier] = image_data
        self.last_active = time.time()
        
        if len(self._user_images) > 20:
            oldest = list(self._user_images.keys())[0]
            del self._user_images[oldest]
        
        return identifier
    
    def store_ai_image(self, image_data: str) -> str:
        identifier = f"<ai_image_{len(self._ai_images) + 1}>"
        self._ai_images[identifier] = image_data
        self.last_active = time.time()
        
        if len(self._ai_images) > 20:
            oldest = list(self._ai_images.keys())[0]
            del self._ai_images[oldest]
        
        return identifier
    
    def resolve_image_identifier(self, identifier: str) -> Optional[str]:
        # 兼容带尖括号和不带尖括号的格式
        # AI 有时会传入 "user_image_1" 而不是 "<user_image_1>"
        if not identifier.startswith('<'):
            identifier = f"<{identifier}>"
        
        if identifier in self._user_images:
            return self._user_images[identifier]
        
        if identifier in self._ai_images:
            return self._ai_images[identifier]
        
        return None
    
    def build_image_list_prompt(self) -> str:
        has_images = self._user_images or self._ai_images
        if not has_images:
            return ""
        
        lines = [
            "",
            "=" * 40,
            "【系统内部信息：可用图片列表】",
            "=" * 40,
            "",
            "⚠️ 严格规则（必须遵守）：",
            "1. 以下标识符仅用于调用 generate_image/edit_image 工具时的参数",
            "2. 绝对禁止在回复中输出这些标识符给用户",
            "3. 如果需要提及图片，请用文字描述（如\"刚才生成的图片\"、\"你发的第一张图\"）",
            "4. 违规输出会被系统过滤，影响回复质量",
            "",
            "可用图片标识符：",
        ]
        
        if self._user_images:
            lines.append("  用户图片：" + ", ".join(self._user_images.keys()))
        if self._ai_images:
            lines.append("  AI生成的图片：" + ", ".join(self._ai_images.keys()))

        lines.extend([
            "",
            "=" * 40,
            "【系统信息结束】",
            "=" * 40,
            ""
        ])
        
        return "\n".join(lines)
    
    def resolve_tool_image_placeholders(self, text: str) -> str:
        return text
    
    def is_expired(self) -> bool:
        if conf.session_timeout <= 0:
            return False
        return time.time() - self.last_active > conf.session_timeout


class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self.continuous_users: Dict[str, bool] = {}
        self.choice_mode_users: Dict[str, bool] = {}
        self.choice_guideline_users: Dict[str, Optional[str]] = {}
    
    def get_session_id(self, user_id: int, group_id: Optional[int] = None) -> str:
        if group_id:
            return f"group_{group_id}_user_{user_id}"
        return f"private_{user_id}"
    
    def get_session(self, user_id: int, group_id: Optional[int] = None, persona: Optional[str] = None) -> Session:
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session
            else:
                del self.sessions[session_id]
                if session_id in self.continuous_users:
                    del self.continuous_users[session_id]
        session = Session(session_id, persona)
        if self.continuous_users.get(session_id, False):
            session.continuous_mode = True
        if self.choice_mode_users.get(session_id, False):
            session.choice_mode_enabled = True
            session.choice_guideline = self.choice_guideline_users.get(session_id, None)
        self.sessions[session_id] = session
        return session
    
    def clear_session(self, user_id: int, group_id: Optional[int] = None) -> bool:
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            del self.sessions[session_id]
            if session_id in self.continuous_users:
                del self.continuous_users[session_id]
            if session_id in self.choice_mode_users:
                del self.choice_mode_users[session_id]
            if session_id in self.choice_guideline_users:
                del self.choice_guideline_users[session_id]
            return True
        return False
    
    def set_continuous_mode(self, user_id: int, group_id: Optional[int] = None, enabled: bool = True) -> bool:
        session_id = self.get_session_id(user_id, group_id)
        self.continuous_users[session_id] = enabled
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                session.continuous_mode = enabled
                return True
        return False
    
    def is_continuous_mode(self, user_id: int, group_id: Optional[int] = None) -> bool:
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session.continuous_mode
            else:
                if session_id in self.continuous_users:
                    del self.continuous_users[session_id]
        return self.continuous_users.get(session_id, False)
    
    def set_choice_mode(self, user_id: int, group_id: Optional[int] = None, enabled: bool = True, guideline: Optional[str] = None) -> bool:
        session_id = self.get_session_id(user_id, group_id)
        self.choice_mode_users[session_id] = enabled
        if enabled and guideline:
            self.choice_guideline_users[session_id] = guideline
        elif not enabled:
            if session_id in self.choice_guideline_users:
                del self.choice_guideline_users[session_id]
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
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session.choice_mode_enabled, session.choice_guideline
            else:
                if session_id in self.choice_mode_users:
                    del self.choice_mode_users[session_id]
                if session_id in self.choice_guideline_users:
                    del self.choice_guideline_users[session_id]
        enabled = self.choice_mode_users.get(session_id, False)
        guideline = self.choice_guideline_users.get(session_id, None)
        return enabled, guideline
    
    def set_last_choices(self, user_id: int, group_id: Optional[int] = None, choices: Dict[int, str] = None) -> bool:
        session_id = self.get_session_id(user_id, group_id)
        
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                session.last_choices = choices or {}
                return True
        return False
    
    def get_last_choices(self, user_id: int, group_id: Optional[int] = None) -> Dict[int, str]:
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if not session.is_expired():
                return session.last_choices
            else:
                del self.sessions[session_id]
                if session_id in self.continuous_users:
                    del self.continuous_users[session_id]
        return {}
    
    def rollback_messages(self, user_id: int, group_id: Optional[int] = None, count: int = 1) -> int:
        session_id = self.get_session_id(user_id, group_id)
        if session_id not in self.sessions:
            return 0
        session = self.sessions[session_id]
        if not session.messages:
            return 0
        system_msg = None
        start_idx = 0
        if session.messages and session.messages[0].get("role") == "system":
            system_msg = session.messages[0]
            start_idx = 1
        messages_to_delete = count * 2
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


session_manager = SessionManager()
