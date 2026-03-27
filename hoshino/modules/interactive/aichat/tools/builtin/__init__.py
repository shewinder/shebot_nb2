"""
AI 内置工具包
自动导入并注册所有内置工具
"""
# 导入所有工具模块，使其自动注册
from . import generate_image
from . import scheduler

__all__ = ["generate_image", "scheduler", "web_search"]
