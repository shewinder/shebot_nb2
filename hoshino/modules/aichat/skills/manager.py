"""
Author: SheBot
Date: 2026-03-31
Description: SKILL 管理器 - 管理 SKILL 生命周期和会话状态
"""
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

from loguru import logger

from .discovery import SkillDiscovery
from .model import Skill


@dataclass
class SessionSkillState:
    """会话级 SKILL 状态"""
    active_skills: Set[str] = field(default_factory=set)  # 已激活的 SKILL 名称
    activation_time: Dict[str, float] = field(default_factory=dict)  # 激活时间
    skill_contents: Dict[str, str] = field(default_factory=dict)  # 已注入的内容


class SkillManager:
    """SKILL 管理器"""
    
    def __init__(self, user_paths: Optional[List[str]] = None):
        # 用户路径（不 git 跟踪），内置路径在 discovery.py 中硬编码
        self.user_paths = user_paths or ["data/skills"]
        self.discovery = SkillDiscovery(self.user_paths)
        self._skills: Dict[str, Skill] = {}
        # 会话级 SKILL 状态: session_id -> SessionSkillState
        self._session_states: Dict[str, SessionSkillState] = {}
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
    
    def _get_session_state(self, session_id: str) -> SessionSkillState:
        """获取或创建会话状态"""
        if session_id not in self._session_states:
            self._session_states[session_id] = SessionSkillState()
        return self._session_states[session_id]
    
    def activate_skill(self, session_id: str, skill_name: str) -> tuple:
        """
        激活 SKILL
        
        Returns:
            (success: bool, message: str, content: Optional[str])
        """
        skill = self._skills.get(skill_name)
        if not skill:
            return False, f"SKILL '{skill_name}' 不存在", None
        
        state = self._get_session_state(session_id)
        
        # 检查是否已激活
        if skill_name in state.active_skills:
            return True, f"SKILL '{skill_name}' 已经激活", skill.content
        
        # 检测循环激活
        if self._would_cause_cycle(session_id, skill_name):
            return False, f"激活 '{skill_name}' 会导致循环依赖，已阻止", None
        
        # 激活 SKILL
        state.active_skills.add(skill_name)
        state.activation_time[skill_name] = time.time()
        state.skill_contents[skill_name] = skill.content
        
        logger.info(f"Session {session_id} 激活 SKILL: {skill_name}")
        return True, f"SKILL '{skill_name}' 已激活", skill.content
    
    def deactivate_skill(self, session_id: str, skill_name: str) -> bool:
        """停用 SKILL"""
        state = self._get_session_state(session_id)
        
        if skill_name not in state.active_skills:
            return False
        
        state.active_skills.discard(skill_name)
        state.activation_time.pop(skill_name, None)
        state.skill_contents.pop(skill_name, None)
        
        logger.info(f"Session {session_id} 停用 SKILL: {skill_name}")
        return True
    
    def get_active_skills(self, session_id: str) -> List[Skill]:
        """获取会话中已激活的 SKILL 列表"""
        state = self._get_session_state(session_id)
        return [self._skills[name] for name in state.active_skills if name in self._skills]
    
    def get_active_skill_names(self, session_id: str) -> Set[str]:
        """获取会话中已激活的 SKILL 名称集合"""
        state = self._get_session_state(session_id)
        return state.active_skills.copy()
    
    def is_skill_active(self, session_id: str, skill_name: str) -> bool:
        """检查 SKILL 是否已激活"""
        state = self._get_session_state(session_id)
        return skill_name in state.active_skills
    
    def get_injected_content(self, session_id: str) -> str:
        """获取需要注入到上下文的 SKILL 内容"""
        state = self._get_session_state(session_id)
        if not state.active_skills:
            return ""
        
        sections = []
        for skill_name in state.active_skills:
            skill = self._skills.get(skill_name)
            content = state.skill_contents.get(skill_name, "")
            if content:
                section_lines = [f"## SKILL: {skill_name}", ""]
                
                # 如果有 execute_script 权限，添加使用说明
                if skill and skill.metadata.has_tool_permission("execute_script"):
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
    
    def clear_session(self, session_id: str) -> None:
        """清理会话状态"""
        if session_id in self._session_states:
            del self._session_states[session_id]
            logger.debug(f"清理会话 SKILL 状态: {session_id}")
    
    def _would_cause_cycle(self, session_id: str, skill_name: str) -> bool:
        """检测激活是否会导致循环依赖"""
        # 简化实现：限制单个会话最多激活 5 个 SKILL
        state = self._get_session_state(session_id)
        if len(state.active_skills) >= 5:
            return True
        return False
    
    def get_active_skills_summary(self, session_id: str) -> str:
        """获取已激活 SKILL 的摘要（用于用户查询）"""
        active = self.get_active_skills(session_id)
        if not active:
            return "当前没有激活的 SKILL"
        
        lines = [f"当前已激活 {len(active)} 个 SKILL："]
        for skill in active:
            lines.append(f"• {skill.metadata.name}: {skill.metadata.description}")
        
        return "\n".join(lines)
    



# 全局 SKILL 管理器实例
skill_manager = SkillManager()
