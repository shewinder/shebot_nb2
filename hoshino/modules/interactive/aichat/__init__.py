"""
AI Chat插件
支持以#开头的消息触发AI对话，支持session管理
"""
import json
import time
from typing import Dict, List, Optional
from pathlib import Path
from loguru import logger

from hoshino import Service, Bot, Event, userdata_dir
from hoshino.util import aiohttpx
from .config import Config

# 加载配置
conf = Config.get_instance('aichat')

# 创建Service
sv = Service('aichat', help_='AI聊天插件，使用#开头触发对话')

# Session数据结构
class Session:
    """对话Session"""
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages: List[Dict[str, str]] = []  # 对话历史
        self.last_active = time.time()  # 最后活跃时间
    
    def add_message(self, role: str, content: str):
        """添加消息到历史"""
        self.messages.append({"role": role, "content": content})
        # 限制历史消息数量
        if len(self.messages) > conf.max_history * 2:  # *2因为包含user和assistant
            self.messages = self.messages[-conf.max_history * 2:]
        self.last_active = time.time()
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if conf.session_timeout <= 0:
            return False
        return time.time() - self.last_active > conf.session_timeout
    
    def to_dict(self) -> dict:
        """转换为字典用于序列化"""
        return {
            "session_id": self.session_id,
            "messages": self.messages,
            "last_active": self.last_active
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """从字典创建Session"""
        session = cls(data["session_id"])
        session.messages = data.get("messages", [])
        session.last_active = data.get("last_active", time.time())
        return session

# Session管理器
class SessionManager:
    """管理所有Session"""
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self.data_file = userdata_dir.joinpath('aichat_sessions.json')
        self.load_sessions()
    
    def get_session_id(self, user_id: int, group_id: Optional[int] = None) -> str:
        """获取session ID"""
        if group_id:
            return f"group_{group_id}_user_{user_id}"
        return f"private_{user_id}"
    
    def get_session(self, user_id: int, group_id: Optional[int] = None) -> Session:
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
        
        # 创建新session
        session = Session(session_id)
        self.sessions[session_id] = session
        return session
    
    def clear_session(self, user_id: int, group_id: Optional[int] = None) -> bool:
        """清除session"""
        session_id = self.get_session_id(user_id, group_id)
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.save_sessions()
            return True
        return False
    
    def save_sessions(self):
        """保存sessions到文件"""
        try:
            data = {
                sid: session.to_dict() 
                for sid, session in self.sessions.items()
                if not session.is_expired()  # 只保存未过期的
            }
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存sessions失败: {e}")
    
    def load_sessions(self):
        """从文件加载sessions"""
        try:
            if not self.data_file.exists():
                return
            
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for sid, session_data in data.items():
                session = Session.from_dict(session_data)
                if not session.is_expired():
                    self.sessions[sid] = session
        except Exception as e:
            logger.error(f"加载sessions失败: {e}")

# 全局Session管理器
session_manager = SessionManager()

async def call_ai_api(messages: List[Dict[str, str]]) -> Optional[str]:
    """调用AI API"""
    if not conf.api_key:
        logger.warning("AI API密钥未配置")
        return None
    
    # 确保messages不为空
    if not messages:
        logger.error("消息列表为空")
        return None
    
    url = f"{conf.api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {conf.api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": conf.model,
        "messages": messages,
        "max_tokens": conf.max_tokens,
        "temperature": conf.temperature
    }
    
    try:
        resp = await aiohttpx.post(url, headers=headers, json=payload)
        if not resp.ok:
            logger.error(f"AI API调用失败: {resp.status_code}, 响应: {resp.text}")
            return None
        
        result = resp.json
        if not result:
            logger.error("AI API返回空结果")
            return None
        
        sv.logger.debug(str(result))
            
        if "choices" in result and len(result["choices"]) > 0:
            message = result["choices"][0].get("message", {})
            if "content" in message:
                return message["content"]
            else:
                logger.error(f"AI API返回格式错误，缺少content字段: {result}")
                return None
        else:
            error_info = result.get("error", {})
            error_msg = error_info.get("message", "未知错误") if error_info else "返回格式错误"
            logger.error(f"AI API返回错误: {error_msg}, 完整响应: {result}")
            return None
    except Exception as e:
        logger.exception(f"调用AI API异常: {e}")
        return None

async def handle_ai_chat(bot: Bot, event: Event):
    """处理AI聊天消息"""
    # 获取消息内容
    msg = str(event.message).strip()
    print(f"ai msg {msg}")
    
    # 检查是否以#开头
    if not msg.startswith('#'):
        return
    
    # 移除#前缀
    user_input = msg[1:].strip()
    if not user_input:
        await bot.send(event, "请输入要询问的内容（#后面）")
        return
    
    # 检查API配置
    if not conf.api_key:
        await bot.send(event, "AI服务未配置，请联系管理员设置API密钥")
        return
    
    # 获取session
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    session = session_manager.get_session(user_id, group_id)
    
    # 添加用户消息
    session.add_message("user", user_input)
    
    # 调用AI API
    response = await call_ai_api(session.messages)
    
    if response is None:
        await bot.send(event, "AI服务暂时不可用，请稍后再试")
        # 移除刚才添加的用户消息
        if session.messages and session.messages[-1].get("role") == "user":
            session.messages.pop()
        return
    
    # 添加AI回复
    session.add_message("assistant", response)
    
    # 保存sessions
    session_manager.save_sessions()
    
    # 发送回复
    try:
        await bot.send(event, response)
    except Exception as e:
        logger.error(f"发送AI回复失败: {e}")

# 注册消息处理器
sv.on_message(priority=10, block=False).handle()(handle_ai_chat)

# 清除session命令
clear_cmd = sv.on_command('清除对话', aliases=('清空对话', '重置对话'), only_group=False)

@clear_cmd.handle()
async def clear_session(bot: Bot, event: Event):
    """清除当前session"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    if session_manager.clear_session(user_id, group_id):
        await bot.send(event, "对话历史已清除")
    else:
        await bot.send(event, "没有找到对话历史")
