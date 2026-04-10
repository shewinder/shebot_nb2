"""
Author: SheBot
Date: 2026-03-31
Description: SKILL 工具权限验证
"""
import re
from pathlib import Path
from typing import Optional

from loguru import logger

from .model import SkillMetadata


class ToolPermissionChecker:
    """工具权限检查器"""
    
    def __init__(self, skill_directory: Path):
        self.skill_directory = skill_directory.resolve()
    
    def check_permission(
        self, 
        metadata: SkillMetadata, 
        tool_name: str, 
        tool_args: dict
    ) -> tuple:
        """
        检查工具调用权限
        
        Returns:
            (allowed: bool, reason: str)
        """
        # 检查基本权限
        if not metadata.has_tool_permission(tool_name):
            return False, f"SKILL '{metadata.name}' 无权使用工具 '{tool_name}'"
        
        # Bash 工具的额外路径检查
        if tool_name == "Bash":
            return self._check_bash_permission(metadata, tool_args)
        
        # Read/Write 工具的路径检查
        if tool_name in ("Read", "Write"):
            return self._check_file_permission(metadata, tool_args)
        
        return True, ""
    
    def _check_bash_permission(self, metadata: SkillMetadata, tool_args: dict) -> tuple:
        """检查 Bash 工具权限"""
        command = tool_args.get("command", "")
        if not command:
            return True, ""
        
        # 获取 SKILL 声明的 Bash 权限模式
        bash_patterns = []
        for pattern in metadata.allowed_tools:
            if pattern.startswith("Bash(") and pattern.endswith(")"):
                inner = pattern[5:-1]  # 提取括号内内容
                bash_patterns.append(inner)
        
        # 如果没有声明 Bash 权限，拒绝执行
        if not bash_patterns:
            return False, "SKILL 未声明 Bash 工具权限"
        
        # 检查是否匹配任何声明的模式
        for pattern in bash_patterns:
            if self._match_bash_pattern(command, pattern):
                return True, ""
        
        return False, f"Bash 命令 '{command}' 不符合 SKILL 声明的权限模式"
    
    def _match_bash_pattern(self, command: str, pattern: str) -> bool:
        """匹配 Bash 命令是否符合声明的模式"""
        # 简化实现：检查命令是否以允许的脚本路径开头
        parts = command.strip().split()
        if not parts:
            return False
        
        # 模式如 "python scripts/*" -> 提取 "scripts/"
        pattern_parts = pattern.split()
        if len(pattern_parts) < 2:
            return False
        
        # 检查命令类型是否匹配（如 python）
        if parts[0] != pattern_parts[0]:
            return False
        
        # 检查脚本路径是否在 SKILL 目录内
        if len(parts) >= 2:
            script_path = parts[1]
            # 转换为绝对路径检查
            if script_path.startswith("/"):
                script_abs = Path(script_path).resolve()
            else:
                script_abs = (self.skill_directory / script_path).resolve()
            
            # 检查是否在 SKILL 目录内
            try:
                script_abs.relative_to(self.skill_directory)
                return True
            except ValueError:
                return False
        
        return False
    
    def _check_file_permission(self, metadata: SkillMetadata, tool_args: dict) -> tuple:
        """检查文件操作权限"""
        path = tool_args.get("path", "")
        if not path:
            return True, ""
        
        # 转换为绝对路径
        if path.startswith("/"):
            file_abs = Path(path).resolve()
        else:
            file_abs = (self.skill_directory / path).resolve()
        
        # 检查是否在 SKILL 目录内
        try:
            file_abs.relative_to(self.skill_directory)
            return True, ""
        except ValueError:
            return False, f"文件路径 '{path}' 超出 SKILL 目录范围"


def create_permission_checker(skill_directory: Path) -> ToolPermissionChecker:
    """创建权限检查器工厂函数"""
    return ToolPermissionChecker(skill_directory)
