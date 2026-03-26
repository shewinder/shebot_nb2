"""
自然语言命令触发插件
使用LLM分析用户消息意图，自动触发对应的命令
"""
from typing import Optional
from loguru import logger

from nonebot import Bot, get_plugin_config, on_message
from nonebot.rule import to_me
from nonebot.adapters import Event

from .config import Config
from .collector import collect_all_commands
from .analyzer import analyze_intent
from .handler import trigger_command, NLCMD_MARKER

# 加载配置
conf = get_plugin_config(Config)


# 缓存命令列表（避免每次请求都重新收集）
_cached_commands: Optional[list] = None


def get_commands() -> list:
    """获取命令列表（带缓存）"""
    global _cached_commands
    if _cached_commands is None:
        _cached_commands = collect_all_commands()
        logger.info(f"收集到 {len(_cached_commands)} 个可用命令")
        logger.debug(f"命令列表: {_cached_commands}")
    return _cached_commands


@on_message(rule=to_me(), block=False, priority=999).handle()
async def handle_nlcmd(bot: Bot, event: Event):
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
    
    try:
        # 获取可用命令列表
        commands = get_commands()
        if not commands:
            logger.warning("没有可用的命令列表")
            return
        
        # 检查是否精确匹配了某个命令
        for command in commands:
            for cmd in command.cmds:
                if cmd in user_message:
                    logger.debug(f"用户输入很可能精确匹配了命令: {user_message} -> {cmd}, 跳过 nlcmd 处理")
                    return
        
        # 调用LLM分析意图
        intent = await analyze_intent(user_message, commands)
        logger.info(f"LLM分析意图: {intent}")
        if not intent:
            logger.debug("LLM分析失败，跳过处理")
            return
        
        # 检查置信度
        confidence = intent.get("confidence", 0.0)
        if confidence < conf.min_confidence:
            logger.debug(f"置信度 {confidence} 低于阈值 {conf.min_confidence}，跳过处理")
            return
        
        # 检查是否精确匹配了某个命令
        if intent and intent.get("skip") == True:
            logger.debug("LLM判断消息精确匹配了命令，跳过 nlcmd 处理")
            return
        
        # 触发命令
        success = await trigger_command(bot, event, intent)
        if success:
            logger.info(f"成功处理自然语言命令: {user_message} -> {intent.get('command_msg', '')}")
        else:
            logger.warning(f"触发命令失败: {intent}")
            
    except Exception as e:
        logger.exception(f"处理自然语言命令异常: {e}")

