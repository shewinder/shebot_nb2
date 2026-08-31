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

    def _sync_discovery_paths(self) -> None:
        """把当前 user_paths 同步给 discovery（路径变更后热重载才能生效）"""
        self.discovery.user_paths = [Path(p) for p in self.user_paths]

    def initialize(self) -> None:
        """初始化，发现所有 SKILL"""
        if self._initialized:
            return
        
        self._sync_discovery_paths()
        self._skills = self.discovery.discover_all()
        self._initialized = True
        logger.info(f"SKILL 管理器初始化完成，共 {len(self._skills)} 个 SKILL")
    
    def reload(self) -> None:
        """重新加载所有 SKILL"""
        self._sync_discovery_paths()
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
        
        # 所有 skill 均可被 AI 触发
        auto_skills = list(self._skills.values())
        
        if not auto_skills:
            return ""
        
        lines = [
            "=" * 40,
            "【SKILL 系统】",
            "=" * 40,
            "",
            "📋 可用 SKILL 列表：",
        ]
        
        for skill in auto_skills:
            lines.append(f"• {skill.metadata.name}: {skill.metadata.description}")
        
        lines.extend([
            "",
            "⚙️ 强制决策流程（每轮回复前必须执行）：",
            "1. 先分析用户本次请求是否匹配某个 SKILL 的功能（生成/处理图片、视频、下载、搜索等专业任务）",
            "2. 用户提供图片/视频等媒体时，同样先判断是否属于某个 SKILL 的输入场景（如提供参考图要求生成/替换视频 → video_generation；要求生成/编辑图片 → image_generation）",
            "3. 匹配到 SKILL：必须调用 activate_skill 激活它，激活后按注入的 SKILL 指导完成实际任务",
            "4. 未匹配到任何 SKILL：才允许按常规方式回答",
            "",
            "🔴 禁止事项（违反即任务失败）：",
            "1. 禁止只做分析/规划/描述而不执行——用户要求生成或处理媒体时，必须激活对应 SKILL 并实际产出结果",
            "2. 禁止用\"我分析一下/让我探测环境/我看看\"等话术代替工具调用",
            "3. 禁止把需要 SKILL 的任务当作普通聊天回答",
            "4. 激活后必须按 SKILL 指导实际执行（调用其脚本/工具），不得只读指导不干活",
            "5. 若执行失败或工具不可用，如实告知失败原因，禁止假装成功",
            "",
            "🔧 激活方法：activate_skill(skill_name=\"xxx\")；已激活的 SKILL 不要重复激活",
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
            
            section_lines = [f"## SKILL: {skill_name}", "", content]
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
