'''
Author: SheBot
Date: 2025-03-14
Description: Web 控制台插件
Github: https://github.com/
'''
from ._log_manager import log_manager

# 启动日志收集（添加 loguru sink）
log_manager.start()

# 初始化 Web 路由
from .app import init_web
init_web()
