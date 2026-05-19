"""
Author: SheBot
Date: 2026-03-31
Description: SKILL 数据模型
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SkillMetadata:
    """SKILL 元数据"""
    name: str                          # 唯一标识
    description: str                   # 一句话描述
    source: str = "local"              # 来源标识 (local/url)
    version: str = ""                  # 版本号
    enabled: bool = True               # 是否启用


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
