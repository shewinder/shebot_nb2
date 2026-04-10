"""
Author: SheBot
Date: 2026-03-31
Description: SKILL 数据模型
"""
from typing import List, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SkillMetadata:
    """SKILL 元数据"""
    name: str                          # 唯一标识
    description: str                   # 一句话描述
    allowed_tools: List[str] = field(default_factory=list)  # 允许的工具
    user_invocable: bool = True        # 用户是否可手动触发
    disable_model_invocation: bool = False  # 是否禁止 AI 自动触发
    source: str = "local"              # 来源标识 (local/clawhub/url)
    version: str = ""                  # 版本号
    enabled: bool = True               # 是否启用
    
    def has_tool_permission(self, tool_name: str) -> bool:
        """检查是否有指定工具的权限"""
        if not self.allowed_tools:
            return False
        
        # 精确匹配
        if tool_name in self.allowed_tools:
            return True
        
        # 模式匹配，如 "Bash(python scripts/*)"
        for pattern in self.allowed_tools:
            if '(' in pattern:
                # 提取工具名前缀
                base_tool = pattern.split('(')[0].strip()
                if tool_name == base_tool:
                    return True
        
        return False


@dataclass
class Skill:
    """SKILL 对象"""
    metadata: SkillMetadata
    content: str                       # SKILL.md 正文内容
    directory: Path                    # SKILL 所在目录
    
    def __hash__(self) -> int:
        return hash(self.metadata.name)
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Skill):
            return False
        return self.metadata.name == other.metadata.name
