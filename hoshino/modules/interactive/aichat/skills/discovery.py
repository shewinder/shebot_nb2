"""
Author: SheBot
Date: 2026-03-31
Description: SKILL 发现和加载模块
"""
import re
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from loguru import logger

from .model import Skill, SkillMetadata


# 内置 SKILL 路径（相对于本文件，git 跟踪）
BUILTIN_SKILL_PATH = Path(__file__).parent


class SkillDiscovery:
    """SKILL 发现器
    
    搜索顺序：
    1. 内置路径（BUILTIN_SKILL_PATH）- 随项目发布，git 跟踪
    2. 用户路径（user_paths）- 用户自定义，不 git 跟踪
    
    同名 SKILL：后加载的覆盖先加载的（用户可覆盖内置）
    """
    
    def __init__(self, user_paths: List[str]):
        # 内置路径 + 用户路径
        self.builtin_path = BUILTIN_SKILL_PATH
        self.user_paths = [Path(p) for p in user_paths]
        self._skills: Dict[str, Skill] = {}
    
    def discover_all(self) -> Dict[str, Skill]:
        """发现所有 SKILL（内置 + 用户）"""
        self._skills = {}
        
        # 1. 先扫描内置路径
        if self.builtin_path.exists():
            logger.debug(f"扫描内置 SKILL 路径: {self.builtin_path}")
            self._discover_in_path(self.builtin_path)
        else:
            logger.warning(f"内置 SKILL 路径不存在: {self.builtin_path}")
        
        # 2. 再扫描用户路径（用户 skill 可覆盖内置）
        for path in self.user_paths:
            if not path.exists():
                logger.debug(f"用户 SKILL 路径不存在，跳过: {path}")
                continue
            
            self._discover_in_path(path)
        
        logger.info(f"共发现 {len(self._skills)} 个 SKILL（内置 + 用户）")
        return self._skills.copy()
    
    def _discover_in_path(self, path: Path) -> None:
        """在指定路径中发现 SKILL"""
        if not path.is_dir():
            return
        
        for item in path.iterdir():
            if not item.is_dir():
                continue
            
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                skill = self._parse_skill(item)
                if skill:
                    # 名称冲突处理：后加载的覆盖先加载的
                    if skill.metadata.name in self._skills:
                        logger.warning(
                            f"SKILL 名称冲突: {skill.metadata.name}, "
                            f"位于 {item} 的 SKILL 将覆盖之前的定义"
                        )
                    self._skills[skill.metadata.name] = skill
    
    def _parse_skill(self, directory: Path) -> Optional[Skill]:
        """解析单个 SKILL"""
        skill_md = directory / "SKILL.md"
        
        try:
            content = skill_md.read_text(encoding='utf-8')
        except Exception as e:
            logger.error(f"读取 SKILL.md 失败 {skill_md}: {e}")
            return None
        
        # 解析 frontmatter
        metadata, body = self._parse_frontmatter(content)
        if metadata is None:
            return None
        
        # 验证必需字段
        if 'name' not in metadata or 'description' not in metadata:
            logger.warning(f"SKILL {directory} 缺少必需字段 name 或 description")
            return None
        
        # 读取 _meta.json 中的额外元数据（如果存在）
        meta_json = directory / "_meta.json"
        extra_meta = {}
        if meta_json.exists():
            try:
                import json
                extra_meta = json.loads(meta_json.read_text(encoding='utf-8'))
            except Exception as e:
                logger.warning(f"读取 _meta.json 失败 {meta_json}: {e}")
        
        # 构建 SkillMetadata
        skill_metadata = SkillMetadata(
            name=metadata['name'],
            description=metadata['description'],
            allowed_tools=metadata.get('allowed-tools', []),
            user_invocable=metadata.get('user-invocable', True),
            disable_model_invocation=metadata.get('disable-model-invocation', False),
            source=extra_meta.get('source', 'local'),
            version=extra_meta.get('version', metadata.get('version', '')),
            enabled=extra_meta.get('enabled', True),
        )
        
        skill = Skill(
            metadata=skill_metadata,
            content=body.strip(),
            directory=directory,
        )
        
        logger.debug(f"成功加载 SKILL: {skill.metadata.name}")
        return skill
    
    def _parse_frontmatter(self, content: str) -> tuple:
        """解析 YAML frontmatter"""
        # 匹配 --- 包围的 frontmatter
        pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(pattern, content, re.DOTALL)
        
        if not match:
            logger.warning("SKILL.md 缺少 YAML frontmatter")
            return None, content
        
        try:
            metadata = yaml.safe_load(match.group(1))
            if not isinstance(metadata, dict):
                logger.warning("SKILL.md frontmatter 不是有效的 YAML 对象")
                return None, content
            
            body = match.group(2)
            return metadata, body
            
        except yaml.YAMLError as e:
            logger.warning(f"解析 SKILL.md frontmatter 失败: {e}")
            return None, content
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """获取指定名称的 SKILL"""
        return self._skills.get(name)
    
    def list_skills(self) -> List[Skill]:
        """列出所有已发现的 SKILL"""
        return list(self._skills.values())
