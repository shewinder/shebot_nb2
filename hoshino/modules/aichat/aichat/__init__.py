"""AI Chat 插件入口

只保留：配置/子系统导入、MCP/SKILL 初始化、生命周期钩子、消息入口。
命令定义已拆分到 commands/（经 service.sv 注册）。
"""
import asyncio
from loguru import logger

from .api import api_manager
from .chat import handle_ai_chat
from .config import Config
from .infra import close_all_gateways
from .mcp import init_mcp_session_manager, mcp_server_manager
from .persona import persona_manager
from .service import sv
from .session import session_manager
from .skills import skill_manager

# 内置工具注册：tools/__init__ 不触发注册（避免与编排层循环导入），
# 必须由插件入口显式导入。注意：不能依赖 commands/search.py 对
# tools.builtin 的间接导入——那会遗漏 mcp_tools（历史回归教训）。
from .tools import builtin  # noqa: F401
from .tools.builtin import mcp_tools  # noqa: F401

conf = Config.get_instance('aichat')


# MCP 初始化函数
async def init_mcp_servers():
    """初始化 MCP servers（预连接 + 渐进式注入）
    
    启动时连接所有启用的 MCP server，确保首次激活时无延迟。
    但工具只在激活后才注入到对话中（渐进式注入）。
    """
    if not conf.enable_mcp:
        logger.info("MCP 功能已禁用")
        return
    
    if not conf.mcp_servers:
        logger.info("未配置 MCP servers")
        return
    
    logger.info(f"正在初始化 MCP servers，共 {len(conf.mcp_servers)} 个配置")
    
    try:
        # 1. 初始化 server_manager（只保存配置）
        mcp_server_manager.initialize(conf.mcp_servers)
        
        # 2. 创建并初始化 session_manager
        init_mcp_session_manager()
        
        # 3. 预连接所有启用的 server（确保首次激活无延迟）
        logger.info("正在预连接所有 MCP servers...")
        
        async def _connect_one(server_config):
            """单个 server 预连接（独立超时，失败不影响其它 server）"""
            try:
                success = await asyncio.wait_for(
                    _connect_server_with_timeout(server_config), timeout=30
                )
                return server_config.id, success
            except asyncio.TimeoutError:
                return server_config.id, False
            except Exception:
                return server_config.id, False

        # 真并行连接：所有 server 同时发起，总耗时 = max(各 server) 而非累加
        results = await asyncio.gather(
            *[_connect_one(sc) for sc in conf.mcp_servers if sc.enabled],
            return_exceptions=True,
        )

        connected_count = 0
        failed_servers = []
        for item in results:
            if not (isinstance(item, tuple) and len(item) == 2):
                continue
            server_id, success = item
            if success:
                connected_count += 1
                logger.info(f"MCP server '{server_id}' 预连接成功")
            else:
                failed_servers.append(server_id)
                logger.warning(f"MCP server '{server_id}' 预连接失败或超时")
        
        logger.info(f"MCP 系统初始化完成：{connected_count}/{len(results)} 个 server 已连接")
        if failed_servers:
            logger.warning(f"连接失败的 servers: {', '.join(failed_servers)}（将在激活时重试）")
        
    except Exception as e:
        logger.exception(f"初始化 MCP 系统失败: {e}")


async def _connect_server_with_timeout(server_config):
    """连接单个 MCP server（带错误处理）"""
    try:
        return await mcp_server_manager.ensure_connected(server_config.id)
    except asyncio.CancelledError:
        raise
    except Exception:
        return False


# SKILL 系统初始化函数
def init_skill_system():
    """初始化 SKILL 系统"""
    if not conf.enable_skills:
        logger.info("SKILL 系统已禁用")
        return
    
    try:
        skill_manager.user_paths = conf.skill_user_paths
        skill_manager.initialize()
        logger.info(f"SKILL 系统初始化完成，内置路径 + 用户路径: {conf.skill_user_paths}")
    except Exception as e:
        logger.exception(f"初始化 SKILL 系统失败: {e}")


# 注册启动时初始化 MCP 和 SKILL
try:
    from nonebot import get_driver
    driver = get_driver()
    
    @driver.on_startup
    async def _init_mcp():
        await init_mcp_servers()
        # 同时初始化 SKILL 系统
        init_skill_system()
        # 启动会话 GC（清理过期会话及其图片/MCP 状态）
        session_manager.start_gc()

    @driver.on_shutdown
    async def _shutdown_mcp():
        await session_manager.stop_gc()
        await mcp_server_manager.stop_all()
        await close_all_gateways()
            
except ImportError:
    pass

# 消息入口：以 # 开头或连续对话模式触发
sv.on_message(priority=10, block=False, only_group=False).handle()(handle_ai_chat)

# 命令注册（import 即注册到 sv）。
# commands 是 namespace package（无 __init__.py）：hoshino/nonebot 的插件
# 发现机制会把含 __init__.py 的子目录识别为独立插件，此处显式逐个导入规避。
from .commands import (  # noqa: E402,F401
    character,
    chat_mode,
    mcp,
    model,
    persona,
    preset,
    search,
    skills,
)
