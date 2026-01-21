"""
自然语言命令触发插件
使用LLM分析用户消息意图，自动触发对应的命令
"""
from typing import Optional
from loguru import logger

from hoshino import Service, Bot, Event, MessageEvent
from .config import Config
from .collector import collect_all_matchers
from .analyzer import analyze_intent
from .handler import trigger_command, NLCMD_MARKER

# 加载配置
conf = Config.get_instance('nlcmd')

# 创建Service
sv = Service('nlcmd', help_='自然语言命令触发，使用LLM理解用户意图并自动执行命令')

# 缓存命令列表（避免每次请求都重新收集）
_cached_commands: Optional[list] = None


def get_commands() -> list:
    """获取命令列表（带缓存）"""
    global _cached_commands
    if _cached_commands is None:
        _cached_commands = collect_all_matchers()
        logger.info(f"收集到 {len(_cached_commands)} 个可用命令")
    return _cached_commands


async def handle_nlcmd(bot: Bot, event: MessageEvent):
    """处理自然语言命令"""
    # 检查是否已经有NLCMD标记（避免递归）
    if hasattr(event, '__dict__') and NLCMD_MARKER in event.__dict__:
        return
    
    # 检查API配置
    if not conf.api_key:
        logger.debug("NLCMD API密钥未配置，跳过处理")
        return
    
    # 获取用户消息
    user_message = str(event.message).strip()
    if not user_message:
        return
    
    # 检查是否已经有命令前缀（避免重复处理）
    # 如果消息已经以命令前缀开头，让其他插件处理
    if user_message.startswith(('/', '！', '!', '#')):
        return
    
    try:
        # 获取可用命令列表
        commands = get_commands()
        if not commands:
            logger.warning("没有可用的命令列表")
            return
        
        # 调用LLM分析意图
        intent = await analyze_intent(user_message, commands)
        if not intent:
            logger.debug("LLM分析失败，跳过处理")
            return
        
        # 检查置信度
        confidence = intent.get("confidence", 0.0)
        if confidence < conf.min_confidence:
            logger.debug(f"置信度 {confidence} 低于阈值 {conf.min_confidence}，跳过处理")
            return
        
        # 触发命令
        success = await trigger_command(bot, event, intent)
        if success:
            logger.info(f"成功处理自然语言命令: {user_message} -> {intent.get('command_msg', '')}")
        else:
            logger.warning(f"触发命令失败: {intent}")
            
    except Exception as e:
        logger.exception(f"处理自然语言命令异常: {e}")


# 注册消息处理器
# priority=999 设置为低优先级，让精确匹配的命令优先处理
# block=False 不阻塞，让其他插件也能处理
# only_to_me=True 只在@机器人或私聊时触发
sv.on_message(priority=999, block=False, only_to_me=True).handle()(handle_nlcmd)
