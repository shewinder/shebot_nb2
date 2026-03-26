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
        
        # 图片分类存储（统一标识符系统）
        self._user_images: Dict[str, str] = {}  # 用户上传的图片：标识符 -> base64
        self._user_image_counter: int = 0
        self._ai_images: Dict[str, str] = {}    # AI/工具生成的图片：标识符 -> base64
        self._ai_image_counter: int = 0
        self._url_images: Dict[str, str] = {}   # 外部 URL 图片：标识符 -> URL
        self._url_image_counter: int = 0
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
    
    def get_images(self) -> List[str]:
        """
        从消息历史中提取所有图片的 base64 URL
        
        Returns:
            图片 base64 data URL 列表（按时间顺序）
        """
        images: List[str] = []
        for msg in self.messages:
            content = msg.get('content')
            if isinstance(content, list):
                # 多模态消息
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'image_url':
                        image_url = part.get('image_url', {}).get('url', '')
                        if image_url and image_url.startswith('data:image'):
                            images.append(image_url)
        return images
    
    def get_image_by_index(self, index: int = -1) -> Optional[str]:
        """
        获取指定索引的图片（从消息历史中提取）
        
        Args:
            index: -1 表示最近一张，-2 表示倒数第二张，以此类推
            
        Returns:
            base64 data URL 或 None
        """
        images = self.get_images()
        if not images:
            return None
        try:
            return images[index]
        except IndexError:
            return None
    
    # ==================== 统一标识符图片存储系统 ====================
    
    def store_user_image(self, image_data: str) -> str:
        """
        存储用户上传的图片
        
        Args:
            image_data: base64 data URL
            
        Returns:
            标识符，如 "<我发的图片-1>"
        """
        self._user_image_counter += 1
        identifier = f"<我发的图片-{self._user_image_counter}>"
        self._user_images[identifier] = image_data
        self.last_active = time.time()
        
        # 限制最多存储 20 张
        if len(self._user_images) > 20:
            oldest = list(self._user_images.keys())[0]
            del self._user_images[oldest]
        
        return identifier
    
    def store_ai_image(self, image_data: str) -> str:
        """
        存储 AI/工具生成的图片
        
        Args:
            image_data: base64 data URL 或 HTTP URL
            
        Returns:
            标识符，如 "<你发的图片-1>"
        """
        self._ai_image_counter += 1
        identifier = f"<你发的图片-{self._ai_image_counter}>"
        self._ai_images[identifier] = image_data
        self.last_active = time.time()
        
        # 限制最多存储 20 张
        if len(self._ai_images) > 20:
            oldest = list(self._ai_images.keys())[0]
            del self._ai_images[oldest]
        
        return identifier
    
    def store_url_image(self, url: str) -> str:
        """
        存储外部 URL 图片
        
        Args:
            url: HTTP URL
            
        Returns:
            标识符，如 "<链接图片-1>"
        """
        self._url_image_counter += 1
        identifier = f"<链接图片-{self._url_image_counter}>"
        self._url_images[identifier] = url
        self.last_active = time.time()
        
        # 限制最多存储 10 张
        if len(self._url_images) > 10:
            oldest = list(self._url_images.keys())[0]
            del self._url_images[oldest]
        
        return identifier
    
    def resolve_image_identifier(self, identifier: str) -> Optional[str]:
        """
        根据标识符获取图片数据
        
        Args:
            identifier: 标识符（如 "<我发的图片-1>"）
            
        Returns:
            base64 data URL 或 HTTP URL，未找到返回 None
        """
        # 从用户图片查找
        if identifier in self._user_images:
            return self._user_images[identifier]
        
        # 从 AI 图片查找
        if identifier in self._ai_images:
            return self._ai_images[identifier]
        
        # 从 URL 图片查找
        if identifier in self._url_images:
            return self._url_images[identifier]
        
        return None
    
    def get_last_user_image(self) -> Optional[Tuple[str, str]]:
        """获取最近的用户图片，返回 (identifier, image_data)"""
        if not self._user_images:
            return None
        identifier = list(self._user_images.keys())[-1]
        return identifier, self._user_images[identifier]
    
    def get_last_ai_image(self) -> Optional[Tuple[str, str]]:
        """获取最近的 AI 图片，返回 (identifier, image_data)"""
        if not self._ai_images:
            return None
        identifier = list(self._ai_images.keys())[-1]
        return identifier, self._ai_images[identifier]
    
    def get_last_url_image(self) -> Optional[Tuple[str, str]]:
        """获取最近的 URL 图片，返回 (identifier, url)"""
        if not self._url_images:
            return None
        identifier = list(self._url_images.keys())[-1]
        return identifier, self._url_images[identifier]
    
    def get_last_image(self) -> Optional[Tuple[str, str]]:
        """获取任意类型最近的一张图片，返回 (identifier, image_data)"""
        # 按优先级：用户图片 > AI 图片 > URL 图片
        if self._user_images:
            return self.get_last_user_image()
        if self._ai_images:
            return self.get_last_ai_image()
        if self._url_images:
            return self.get_last_url_image()
        return None
    
    def build_image_list_prompt(self) -> str:
        """
        构建当前可用图片列表的提示词
        
        Returns:
            图片列表提示词，如果没有图片返回空字符串
        """
        lines = []
        has_images = self._user_images or self._ai_images or self._url_images
        
        if not has_images:
            return ""
        
        lines.append("\n[当前可用图片]")
        lines.append("你可以使用以下标识符引用图片：")
        lines.append("")
        
        if self._user_images:
            lines.append("我（用户）发送的图片：")
            for identifier in self._user_images:
                lines.append(f"  - {identifier}")
            lines.append("")
        
        if self._url_images:
            lines.append("引用消息中的图片：")
            for identifier in self._url_images:
                lines.append(f"  - {identifier}")
            lines.append("")
        
        if self._ai_images:
            lines.append("你（AI）之前生成的图片：")
            for identifier in self._ai_images:
                lines.append(f"  - {identifier}")
            lines.append("")
        
        lines.append("重要提示：")
        lines.append("- 这些标识符仅用于调用工具（如 edit_image）时作为参数传递")
        lines.append("- 不要直接在回复内容中输出标识符给用户看")
        lines.append("- 如果你需要引用某张图片，请描述图片内容，不要显示标识符")
        lines.append("[图片列表结束]\n")
        
        return "\n".join(lines)
    
    # ==================== 兼容性方法（保留） ====================
    
    def resolve_tool_image_placeholders(self, text: str) -> str:
        """
        将文本中的工具图片占位符替换为真实 base64
        用于发送 QQ 消息前（兼容性方法）
        
        Args:
            text: 包含占位符的文本
            
        Returns:
            替换后的文本
        """
        # 新的 AI 图片标识符不需要替换，因为不会出现在发送给用户的文本中
        return text
    
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
            else:
                # session已过期，清理连续对话模式状态
                if session_id in self.continuous_users:
                    del self.continuous_users[session_id]
        
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
            else:
                # session已过期，清理选项模式状态
                if session_id in self.choice_mode_users:
                    del self.choice_mode_users[session_id]
                if session_id in self.choice_guideline_users:
                    del self.choice_guideline_users[session_id]
        
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
            else:
                # session已过期，清理session和连续对话状态
                del self.sessions[session_id]
                if session_id in self.continuous_users:
                    del self.continuous_users[session_id]
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
