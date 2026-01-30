"""
AI Chat插件
支持以#开头的消息触发AI对话，支持session管理
"""
import json
import time
from typing import Dict, List, Optional, Tuple
from loguru import logger

from hoshino import Service, Bot, Event, userdata_dir
from hoshino.permission import ADMIN, SUPERUSER
from hoshino.util import aiohttpx
from .config import Config

# 加载配置
conf = Config.get_instance('aichat')

# 创建Service
sv = Service('aichat', help_='AI聊天插件，使用#开头触发对话')

# Session数据结构
class Session:
    """对话Session"""
    def __init__(self, session_id: str, persona: Optional[str] = None):
        self.session_id = session_id
        self.messages: List[Dict[str, str]] = []  # 对话历史
        self.last_active = time.time()  # 最后活跃时间
        # 如果有人格，在初始化时添加system message
        if persona:
            self.messages.append({"role": "system", "content": persona})
    
    def add_message(self, role: str, content: str):
        """添加消息到历史"""
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

# Session管理器
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

# Persona管理器
class PersonaManager:
    """管理AI人格设置（持久化存储）"""
    def __init__(self):
        self.personas: Dict[str, str] = {}  # key: persona_id, value: persona_text
        self.saved_personas: Dict[str, Dict[str, str]] = {}  # key: user_id, value: {name: persona_text}
        self.data_file = userdata_dir.joinpath('aichat_personas.json')
        self.saved_personas_file = userdata_dir.joinpath('aichat_saved_personas.json')
        self.load_personas()
        self.load_saved_personas()
    
    def _get_user_persona_id(self, user_id: int, group_id: Optional[int] = None) -> str:
        """获取用户人格ID"""
        if group_id:
            return f"{user_id}_{group_id}"
        return f"private_{user_id}"
    
    def _get_group_persona_id(self, group_id: int) -> str:
        """获取群组默认人格ID"""
        return f"group_{group_id}"
    
    def _get_global_persona_id(self) -> str:
        """获取全局默认人格ID"""
        return "global_default"
    
    def get_persona(self, user_id: int, group_id: Optional[int] = None) -> Optional[str]:
        """获取当前用户的人格（按优先级：用户 > 群组 > 全局）"""
        # 1. 检查用户人格
        user_persona_id = self._get_user_persona_id(user_id, group_id)
        if user_persona_id in self.personas:
            persona = self.personas[user_persona_id]
            if persona and persona.strip():
                return persona.strip()
        
        # 2. 检查群组默认人格（仅群聊）
        if group_id:
            group_persona_id = self._get_group_persona_id(group_id)
            if group_persona_id in self.personas:
                persona = self.personas[group_persona_id]
                if persona and persona.strip():
                    return persona.strip()
        
        # 3. 检查全局默认人格
        global_persona_id = self._get_global_persona_id()
        if global_persona_id in self.personas:
            persona = self.personas[global_persona_id]
            if persona and persona.strip():
                return persona.strip()
        
        # 4. 检查配置文件中的默认人格
        if conf.default_persona and conf.default_persona.strip():
            return conf.default_persona.strip()
        
        return None
    
    def set_user_persona(self, user_id: int, group_id: Optional[int], persona: str) -> bool:
        """设置用户人格"""
        user_persona_id = self._get_user_persona_id(user_id, group_id)
        self.personas[user_persona_id] = persona.strip()
        self.save_personas()
        return True
    
    def set_group_default_persona(self, group_id: int, persona: str) -> bool:
        """设置群组默认人格"""
        group_persona_id = self._get_group_persona_id(group_id)
        self.personas[group_persona_id] = persona.strip()
        self.save_personas()
        return True
    
    def set_global_default_persona(self, persona: str) -> bool:
        """设置全局默认人格"""
        global_persona_id = self._get_global_persona_id()
        self.personas[global_persona_id] = persona.strip()
        self.save_personas()
        return True
    
    def clear_user_persona(self, user_id: int, group_id: Optional[int] = None) -> bool:
        """清除用户人格（使用默认）"""
        user_persona_id = self._get_user_persona_id(user_id, group_id)
        if user_persona_id in self.personas:
            del self.personas[user_persona_id]
            self.save_personas()
            return True
        return False
    
    def get_user_persona_info(self, user_id: int, group_id: Optional[int] = None) -> Dict[str, Optional[str]]:
        """获取用户人格信息（包括所有层级）"""
        user_persona_id = self._get_user_persona_id(user_id, group_id)
        user_persona = self.personas.get(user_persona_id)
        
        group_persona = None
        if group_id:
            group_persona_id = self._get_group_persona_id(group_id)
            group_persona = self.personas.get(group_persona_id)
        
        global_persona_id = self._get_global_persona_id()
        global_persona = self.personas.get(global_persona_id)
        
        config_persona = conf.default_persona if conf.default_persona else None
        
        return {
            "user": user_persona,
            "group": group_persona,
            "global": global_persona,
            "config": config_persona,
            "effective": self.get_persona(user_id, group_id)
        }
    
    def save_personas(self):
        """保存人格设置到文件"""
        try:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.personas, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存人格设置失败: {e}")
    
    def load_personas(self):
        """从文件加载人格设置"""
        try:
            if not self.data_file.exists():
                return
            
            with open(self.data_file, 'r', encoding='utf-8') as f:
                self.personas = json.load(f)
        except Exception as e:
            logger.error(f"加载人格设置失败: {e}")
            self.personas = {}
    
    def _get_user_key(self, user_id: int, group_id: Optional[int] = None) -> str:
        """获取用户保存人格的key（全局，不区分群组）"""
        return str(user_id)
    
    def save_persona(self, user_id: int, group_id: Optional[int], name: str, persona: str) -> Tuple[bool, str]:
        """保存人格到用户的人格列表
        返回: (是否成功, 错误信息)
        """
        user_key = self._get_user_key(user_id, group_id)
        
        # 检查名称是否为空
        if not name or not name.strip():
            return False, "人格名称不能为空"
        
        name = name.strip()
        
        # 获取用户已保存的人格
        if user_key not in self.saved_personas:
            self.saved_personas[user_key] = {}
        
        user_personas = self.saved_personas[user_key]
        
        # 如果名称已存在，直接更新
        if name in user_personas:
            user_personas[name] = persona.strip()
            self.save_saved_personas()
            return True, f"人格 '{name}' 已更新"
        
        # 检查是否超过最大数量
        if len(user_personas) >= conf.max_saved_personas:
            return False, f"已保存 {len(user_personas)} 个人格，最多只能保存 {conf.max_saved_personas} 个。请先删除一些人格或使用已有名称更新。"
        
        # 保存新人格
        user_personas[name] = persona.strip()
        self.save_saved_personas()
        return True, f"人格 '{name}' 已保存"
    
    def get_saved_personas(self, user_id: int, group_id: Optional[int] = None) -> Dict[str, str]:
        """获取用户保存的所有人格"""
        user_key = self._get_user_key(user_id, group_id)
        return self.saved_personas.get(user_key, {}).copy()
    
    def get_saved_persona(self, user_id: int, group_id: Optional[int], name: str) -> Optional[str]:
        """获取用户保存的指定人格"""
        user_key = self._get_user_key(user_id, group_id)
        user_personas = self.saved_personas.get(user_key, {})
        return user_personas.get(name)
    
    def delete_saved_persona(self, user_id: int, group_id: Optional[int], name: str) -> Tuple[bool, str]:
        """删除用户保存的人格
        返回: (是否成功, 错误信息)
        """
        user_key = self._get_user_key(user_id, group_id)
        
        if user_key not in self.saved_personas:
            return False, "未找到保存的人格"
        
        user_personas = self.saved_personas[user_key]
        
        if name not in user_personas:
            return False, f"未找到名为 '{name}' 的人格"
        
        del user_personas[name]
        
        # 如果用户没有保存的人格了，删除该用户的key
        if not user_personas:
            del self.saved_personas[user_key]
        
        self.save_saved_personas()
        return True, f"人格 '{name}' 已删除"
    
    def save_saved_personas(self):
        """保存用户人格列表到文件"""
        try:
            self.saved_personas_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.saved_personas_file, 'w', encoding='utf-8') as f:
                json.dump(self.saved_personas, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存用户人格列表失败: {e}")
    
    def load_saved_personas(self):
        """从文件加载用户人格列表"""
        try:
            if not self.saved_personas_file.exists():
                return
            
            with open(self.saved_personas_file, 'r', encoding='utf-8') as f:
                self.saved_personas = json.load(f)
        except Exception as e:
            logger.error(f"加载用户人格列表失败: {e}")
            self.saved_personas = {}

# 全局Persona管理器
persona_manager = PersonaManager()

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
    
    # 获取用户ID和群组ID
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    # 获取用户人格
    persona = persona_manager.get_persona(user_id, group_id)
    
    # 获取或创建session（如果是新session会自动应用人格）
    session = session_manager.get_session(user_id, group_id, persona)
    
    # 添加用户消息
    session.add_message("user", user_input)
    
    # 调用AI API（直接使用session.messages，因为人格已经在session中）
    response = await call_ai_api(session.messages)
    
    if response is None:
        await bot.send(event, "AI服务暂时不可用，请稍后再试")
        # 移除刚才添加的用户消息
        if session.messages and session.messages[-1].get("role") == "user":
            session.messages.pop()
        return
    
    # 添加AI回复
    session.add_message("assistant", response)
    
    # 发送回复
    try:
        await bot.send(event, response)
    except Exception as e:
        logger.error(f"发送AI回复失败: {e}")

# 注册消息处理器
sv.on_message(priority=10, block=False, only_group=False).handle()(handle_ai_chat)

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

# 设置用户人格命令
set_persona_cmd = sv.on_command('设置人格', aliases=('设置AI人格',), only_group=False)

@set_persona_cmd.handle()
async def set_persona(bot: Bot, event: Event):
    """设置用户人格"""
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await set_persona_cmd.finish("请提供人格描述，例如：设置人格 你是一个友好的助手")
        return
    
    persona_text = args[1].strip()
    if not persona_text:
        await set_persona_cmd.finish("人格描述不能为空")
        return
    
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    persona_manager.set_user_persona(user_id, group_id, persona_text)
    
    # 清除当前session，以便新人格生效
    session_manager.clear_session(user_id, group_id)
    
    await set_persona_cmd.finish(f"人格设置成功！\n当前人格：{persona_text}")

# 设置群组默认人格命令（需要管理员权限）
set_group_persona_cmd = sv.on_command('设置群默认人格', aliases=('设置群组默认人格',), permission=ADMIN, only_group=True)

@set_group_persona_cmd.handle()
async def set_group_persona(bot: Bot, event: Event):
    """设置群组默认人格（支持使用已保存的人格名称）"""
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await set_group_persona_cmd.finish("请提供人格描述或已保存的人格名称，例如：\n设置群默认人格 你是一个友好的助手\n设置群默认人格 猫娘（使用已保存的人格）")
        return
    
    input_text = args[1].strip()
    if not input_text:
        await set_group_persona_cmd.finish("人格描述不能为空")
        return
    
    user_id = event.user_id
    group_id = event.group_id
    
    # 先尝试查找已保存的人格
    saved_persona = persona_manager.get_saved_persona(user_id, None, input_text)
    
    if saved_persona:
        # 使用已保存的人格
        persona_text = saved_persona
        persona_manager.set_group_default_persona(group_id, persona_text)
        await set_group_persona_cmd.finish(f"群组默认人格设置成功！\n使用已保存的人格：{input_text}\n人格内容：{persona_text[:100]}{'...' if len(persona_text) > 100 else ''}")
    else:
        # 当作人格描述处理
        persona_text = input_text
        persona_manager.set_group_default_persona(group_id, persona_text)
        await set_group_persona_cmd.finish(f"群组默认人格设置成功！\n当前人格：{persona_text}")

# 设置全局默认人格命令（需要超级用户权限）
set_global_persona_cmd = sv.on_command('设置全局默认人格', aliases=('设置全局人格',), permission=SUPERUSER, only_group=False)

@set_global_persona_cmd.handle()
async def set_global_persona(bot: Bot, event: Event):
    """设置全局默认人格（支持使用已保存的人格名称）"""
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await set_global_persona_cmd.finish("请提供人格描述或已保存的人格名称，例如：\n设置全局默认人格 你是一个友好的助手\n设置全局默认人格 猫娘（使用已保存的人格）")
        return
    
    input_text = args[1].strip()
    if not input_text:
        await set_global_persona_cmd.finish("人格描述不能为空")
        return
    
    user_id = event.user_id
    
    # 先尝试查找已保存的人格
    saved_persona = persona_manager.get_saved_persona(user_id, None, input_text)
    
    if saved_persona:
        # 使用已保存的人格
        persona_text = saved_persona
        persona_manager.set_global_default_persona(persona_text)
        await set_global_persona_cmd.finish(f"全局默认人格设置成功！\n使用已保存的人格：{input_text}\n人格内容：{persona_text[:100]}{'...' if len(persona_text) > 100 else ''}")
    else:
        # 当作人格描述处理
        persona_text = input_text
        persona_manager.set_global_default_persona(persona_text)
        await set_global_persona_cmd.finish(f"全局默认人格设置成功！\n当前人格：{persona_text}")

# 查看人格命令
view_persona_cmd = sv.on_command('查看人格', aliases=('查看AI人格', '当前人格'), only_group=False)

@view_persona_cmd.handle()
async def view_persona(bot: Bot, event: Event):
    """查看当前生效的人格"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    effective_persona = persona_manager.get_persona(user_id, group_id)
    
    if effective_persona:
        await view_persona_cmd.finish(f"当前生效的人格：\n{effective_persona}")
    else:
        await view_persona_cmd.finish("未设置人格，使用默认行为")

# 清除人格命令
clear_persona_cmd = sv.on_command('清除人格', aliases=('清除AI人格',), only_group=False)

@clear_persona_cmd.handle()
async def clear_persona(bot: Bot, event: Event):
    """清除用户人格设置"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    if persona_manager.clear_user_persona(user_id, group_id):
        # 清除当前session，以便使用默认人格
        session_manager.clear_session(user_id, group_id)
        await clear_persona_cmd.finish("人格已清除，将使用默认人格")
    else:
        await clear_persona_cmd.finish("未设置用户人格，无需清除")

# 保存人格命令
save_persona_cmd = sv.on_command('保存人格', aliases=('保存AI人格',), only_group=False)

@save_persona_cmd.handle()
async def save_persona(bot: Bot, event: Event):
    """保存人格到用户的人格列表"""
    args = str(event.message).strip().split(maxsplit=2)
    if len(args) < 3:
        await save_persona_cmd.finish(f"请提供人格名称和描述，例如：保存人格 猫娘 你是一个可爱的猫娘\n最多可保存 {conf.max_saved_personas} 个人格")
        return
    
    name = args[1].strip()
    persona_text = args[2].strip()
    
    if not persona_text:
        await save_persona_cmd.finish("人格描述不能为空")
        return
    
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    success, msg = persona_manager.save_persona(user_id, group_id, name, persona_text)
    await save_persona_cmd.finish(msg)

# 列出已保存人格命令
list_personas_cmd = sv.on_command('列出人格', aliases=('查看保存的人格', '已保存人格', '人格列表'), only_group=False)

@list_personas_cmd.handle()
async def list_personas(bot: Bot, event: Event):
    """列出用户保存的所有人格"""
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    saved_personas = persona_manager.get_saved_personas(user_id, group_id)
    
    if not saved_personas:
        await list_personas_cmd.finish(f"你还没有保存任何人格。\n使用「保存人格 名称 描述」来保存人格，最多可保存 {conf.max_saved_personas} 个。")
        return
    
    lines = [f"已保存的人格（{len(saved_personas)}/{conf.max_saved_personas}）："]
    for i, (name, persona) in enumerate(saved_personas.items(), 1):
        # 截断过长的描述
        preview = persona[:50] + "..." if len(persona) > 50 else persona
        lines.append(f"{i}. {name}: {preview}")
    
    lines.append(f"\n使用「使用人格 名称」来快捷设置人格")
    await list_personas_cmd.finish("\n".join(lines))

# 使用已保存人格命令
use_persona_cmd = sv.on_command('使用人格', aliases=('切换人格', '应用人格'), only_group=False)

@use_persona_cmd.handle()
async def use_persona(bot: Bot, event: Event):
    """使用已保存的人格"""
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await use_persona_cmd.finish("请提供人格名称，例如：使用人格 猫娘\n使用「列出人格」查看已保存的人格")
        return
    
    name = args[1].strip()
    
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    persona_text = persona_manager.get_saved_persona(user_id, group_id, name)
    
    if not persona_text:
        await use_persona_cmd.finish(f"未找到名为 '{name}' 的已保存人格。\n使用「列出人格」查看已保存的人格")
        return
    
    # 设置为当前人格
    persona_manager.set_user_persona(user_id, group_id, persona_text)
    
    # 清除当前session，以便新人格生效
    session_manager.clear_session(user_id, group_id)
    
    await use_persona_cmd.finish(f"已切换到人格 '{name}'\n人格内容：{persona_text[:100]}{'...' if len(persona_text) > 100 else ''}")

# 删除已保存人格命令
delete_persona_cmd = sv.on_command('删除人格', aliases=('移除人格', '删除保存的人格'), only_group=False)

@delete_persona_cmd.handle()
async def delete_persona(bot: Bot, event: Event):
    """删除已保存的人格"""
    args = str(event.message).strip().split(maxsplit=1)
    if len(args) < 2:
        await delete_persona_cmd.finish("请提供人格名称，例如：删除人格 猫娘\n使用「列出人格」查看已保存的人格")
        return
    
    name = args[1].strip()
    
    user_id = event.user_id
    group_id = getattr(event, 'group_id', None)
    
    success, msg = persona_manager.delete_saved_persona(user_id, group_id, name)
    await delete_persona_cmd.finish(msg)
