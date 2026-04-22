"""
Author: SheBot
Date: 2026-03-31
Description: SKILL 管理器 - 管理 SKILL 元数据发现与查询

注意：per-session 激活状态已下放到 Session 类，本管理器只保留全局 SKILL 元数据。
"""
from typing import Dict, List, Optional, Set
from pathlib import Path

from loguru import logger

from .discovery import SkillDiscovery
from .model import Skill


class SkillManager:
    """SKILL 管理器 - 全局元数据中心"""
    
    def __init__(self, user_paths: Optional[List[str]] = None):
        # 用户路径（不 git 跟踪），内置路径在 discovery.py 中硬编码
        self.user_paths = user_paths or ["data/skills"]
        self.discovery = SkillDiscovery(self.user_paths)
        self._skills: Dict[str, Skill] = {}
        self._initialized = False
    
    def initialize(self) -> None:
        """初始化，发现所有 SKILL"""
        if self._initialized:
            return
        
        self._skills = self.discovery.discover_all()
        self._initialized = True
        logger.info(f"SKILL 管理器初始化完成，共 {len(self._skills)} 个 SKILL")
    
    def reload(self) -> None:
        """重新加载所有 SKILL"""
        self._skills = self.discovery.discover_all()
        logger.info(f"SKILL 重新加载完成，共 {len(self._skills)} 个 SKILL")
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """获取指定 SKILL"""
        return self._skills.get(name)
    
    def list_skills(self) -> List[Skill]:
        """列出所有可用 SKILL"""
        return list(self._skills.values())
    
    def get_metadata_summary(self) -> str:
        """获取元数据摘要（用于 AI 选择）"""
        if not self._skills:
            return ""
        
        # 过滤出 AI 可自动触发的 SKILL
        auto_skills = [
            skill for skill in self._skills.values()
            if not skill.metadata.disable_model_invocation
        ]
        
        if not auto_skills:
            return ""
        
        lines = [
            "=" * 40,
            "【SKILL 系统】",
            "=" * 40,
            "",
            "📋 可用 SKILL 列表（AI 可根据用户意图自动激活）：",
        ]
        
        for skill in auto_skills:
            lines.append(f"• {skill.metadata.name}: {skill.metadata.description}")
        
        lines.extend([
            "",
            "💡 使用指导：",
            "1. 当用户需求与某个 SKILL 功能匹配时，直接使用 activate_skill 工具激活它",
            "2. 激活后，SKILL 的详细指导内容会注入到上下文中",
            "3. 如果当前没有合适的 SKILL，按常规方式回答",
            "4. 不要重复激活已激活的 SKILL",
            "",
            "🔧 使用方法：activate_skill(skill_name=\"xxx\")",
        ])
        
        return "\n".join(lines)
    
    def get_injected_content(self, active_skills: Set[str]) -> str:
        """获取需要注入到上下文的 SKILL 内容
        
        Args:
            active_skills: 已激活的 SKILL 名称集合（由 Session 提供）
        
        Returns:
            组装好的注入文本
        """
        if not active_skills:
            return ""
        
        sections = []
        for skill_name in active_skills:
            skill = self._skills.get(skill_name)
            if not skill:
                continue
            content = skill.content
            if not content:
                continue
            
            section_lines = [f"## SKILL: {skill_name}", ""]
            
            # 如果有 execute_script 权限，添加使用说明
            if skill.metadata.has_tool_permission("execute_script"):
                section_lines.extend([
                    "### 脚本执行说明",
                    f"本 SKILL 支持使用 `execute_script` 工具执行目录下的脚本。",
                    f"",
                    f"**使用示例：**",
                    f"```python",
                    f'execute_script(skill_name="{skill_name}", script_path="scripts/example.py", args=["arg1"])',
                    f"```",
                    f"",
                    f"**注意事项：**",
                    f"- `skill_name` 必须填写 `{skill_name}`",
                    f"- `script_path` 是相对于 SKILL 目录的相对路径",
                    f"- 只能访问本 SKILL 目录下的文件",
                    f"",
                ])
            
            section_lines.append(content)
            sections.append("\n".join(section_lines))
        
        if not sections:
            return ""
        
        return "\n\n".join([
            "=" * 40,
            "【已激活的 SKILL 指导】",
            "=" * 40,
            "",
        ] + sections + [
            "",
            "=" * 40,
            "【SKILL 指导结束】",
            "=" * 40,
        ])
    
    def get_active_skills_summary(self, active_skills: Set[str]) -> str:
        """获取已激活 SKILL 的摘要（用于用户查询）
        
        Args:
            active_skills: 已激活的 SKILL 名称集合
        """
        if not active_skills:
            return "当前没有激活的 SKILL"
        
        skills = [self._skills[name] for name in active_skills if name in self._skills]
        lines = [f"当前已激活 {len(skills)} 个 SKILL："]
        for skill in skills:
            lines.append(f"• {skill.metadata.name}: {skill.metadata.description}")
        
        return "\n".join(lines)


# 全局 SKILL 管理器实例
skill_manager = SkillManager()
