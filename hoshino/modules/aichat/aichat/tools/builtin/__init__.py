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
from . import skill_admin
from . import web_search
from . import execute_script
from . import curl_tool
from . import store_images
from . import preference_tools
from . import background_task
from . import memory_tools
from . import delegate_task
from . import groupmsg

__all__ = ["scheduler", "weather", "environment", "service_manage", "skill_tools", "skill_admin", "web_search", "execute_script", "curl_tool", "store_images", "preference_tools", "background_task", "memory_tools", "delegate_task", "groupmsg"]
