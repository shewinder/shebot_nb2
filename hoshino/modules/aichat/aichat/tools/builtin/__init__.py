"""
AI 内置工具包
自动导入并注册所有内置工具
"""
# 导入所有工具模块，使其自动注册
from . import scheduler
from . import weather
from . import environment
from . import service_manage
from . import skill_tools
from . import web_search
from . import execute_script
from . import broadcast
from . import fetch_url
from . import send_images
from . import file_storage

__all__ = ["scheduler", "weather", "environment", "service_manage", "skill_tools", "web_search", "execute_script", "broadcast", "fetch_url", "send_images", "file_storage"]
