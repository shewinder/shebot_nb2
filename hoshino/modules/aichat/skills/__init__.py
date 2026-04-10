"""
SKILL 系统 - AI 能力扩展机制

允许用户通过 Markdown 文件和脚本扩展 AI 能力，
支持渐进式加载和细粒度权限控制。
"""
from .clawhub import ClawHubClient, clawhub_client
from .discovery import SkillDiscovery
from .installer import SkillInstaller, get_installer
from .manager import SkillManager, skill_manager
from .model import Skill, SkillMetadata
from .permissions import ToolPermissionChecker

__all__ = [
    "Skill",
    "SkillMetadata",
    "SkillDiscovery",
    "SkillManager",
    "skill_manager",
    "ToolPermissionChecker",
    "ClawHubClient",
    "clawhub_client",
    "SkillInstaller",
    "get_installer",
]
