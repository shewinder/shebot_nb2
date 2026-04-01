"""
Author: SheBot
Date: 2026-03-31
Description: Skill 安装器 - 处理从各种来源安装 skill
"""
import json
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from loguru import logger

from hoshino.util import aiohttpx
from .clawhub import clawhub_client


class InstallResult:
    """安装结果"""
    def __init__(self, success: bool, message: str, skill_name: str = "", version: str = ""):
        self.success = success
        self.message = message
        self.skill_name = skill_name
        self.version = version
    
    def __bool__(self):
        return self.success


class SkillInstaller:
    """Skill 安装器"""
    
    def __init__(self, install_path: Path):
        self.install_path = Path(install_path)
        self.install_path.mkdir(parents=True, exist_ok=True)
    
    async def install(self, source: str) -> InstallResult:
        """从各种来源安装 skill
        
        支持的来源格式：
        - ClawHub: clawhub:user/skill-name 或 user/skill-name
        - URL: http(s)://.../skill.zip
        - 本地路径: /path/to/skill
        
        Returns:
            InstallResult
        """
        source = source.strip()
        
        # 检查是否是 ClawHub 引用
        if source.startswith("clawhub:") or "/" in source:
            return await self.install_from_clawhub(source)
        
        # 检查是否是 URL
        if source.startswith(("http://", "https://")):
            return await self.install_from_url(source)
        
        # 检查是否是本地路径
        local_path = Path(source)
        if local_path.exists():
            return await self.install_from_local(local_path)
        
        # 尝试作为 skill 名称从 ClawHub 搜索
        return await self.install_from_clawhub(source)
    
    async def install_from_clawhub(self, ref: str) -> InstallResult:
        """从 ClawHub 安装 skill
        
        支持的格式:
        - clawhub:skill-name
        - skill-name
        
        注意: ClawHub 使用 CLI 方式，skill 名称就是 slug
        """
        slug = clawhub_client.parse_clawhub_reference(ref)
        
        logger.info(f"从 ClawHub 安装 skill: {slug}")
        
        # 直接尝试安装
        target_dir = self._get_target_dir(slug.replace("/", "-"))
        
        # 检查是否已存在
        if target_dir.exists():
            return InstallResult(False, f"Skill '{slug}' 已存在，请先删除旧版本")
        
        success, version = await clawhub_client.download_skill(slug, target_dir)
        if success:
            return InstallResult(True, f"安装成功", slug, version)
        else:
            # 可能是 CLI 未安装，尝试 explore 查找
            if "CLI" in version or "不可用" in version:
                logger.info(f"CLI 不可用，尝试从 explore 查找")
                explore_results = await clawhub_client.explore_skills(limit=50)
                
                # 查找匹配的 skill
                for skill in explore_results:
                    if slug.lower() in skill.slug.lower() or slug.lower() in skill.name.lower():
                        target_dir = self._get_target_dir(skill.slug.replace("/", "-"))
                        if target_dir.exists():
                            return InstallResult(False, f"Skill '{skill.slug}' 已存在")
                        
                        success, version = await clawhub_client.download_skill(skill.slug, target_dir)
                        if success:
                            return InstallResult(True, f"安装成功 (匹配: {skill.slug})", skill.name or skill.slug, version)
                
                return InstallResult(False, f"ClawHub CLI 未安装。请使用以下方式之一：\n1. 安装 CLI: npm install -g clawhub\n2. 使用 URL 安装: #安装技能 https://.../skill.zip\n3. 使用本地路径: #安装技能 ./path/to/skill")
            
            return InstallResult(False, f"从 ClawHub 安装失败: {version}")
    
    async def install_from_url(self, url: str) -> InstallResult:
        """从 URL 安装 skill"""
        parsed = urlparse(url)
        
        try:
            resp = await aiohttpx.get(url)
            if not resp.ok:
                return InstallResult(False, f"下载失败: HTTP {resp.status_code}")
            
            # 判断是压缩包还是单个文件
            content_type = resp.headers.get("Content-Type", "")
            url_path = parsed.path.lower()
            
            if url_path.endswith(".zip") or "zip" in content_type:
                return await self._install_from_zip(resp.content)
            elif url_path.endswith((".tar.gz", ".tgz")):
                return await self._install_from_tar(resp.content)
            elif url_path.endswith(".md"):
                # 单个 SKILL.md 文件
                return await self._install_from_content(resp.text)
            else:
                # 尝试作为 zip 处理
                return await self._install_from_zip(resp.content)
                
        except Exception as e:
            logger.exception(f"从 URL 安装失败: {e}")
            return InstallResult(False, f"安装失败: {e}")
    
    async def install_from_local(self, path: Path) -> InstallResult:
        """从本地路径安装 skill"""
        path = Path(path)
        
        if not path.exists():
            return InstallResult(False, f"路径不存在: {path}")
        
        # 验证 skill 结构
        if path.is_dir():
            skill_md = path / "SKILL.md"
            if not skill_md.exists():
                return InstallResult(False, f"目录中缺少 SKILL.md: {path}")
            
            # 解析 skill 名称
            try:
                content = skill_md.read_text(encoding='utf-8')
                metadata = self._parse_frontmatter(content)
                if not metadata or 'name' not in metadata:
                    return InstallResult(False, "SKILL.md 缺少 name 字段")
                
                skill_name = metadata['name']
                target_dir = self._get_target_dir(skill_name)
                
                # 检查是否已存在
                if target_dir.exists():
                    return InstallResult(False, f"Skill '{skill_name}' 已存在")
                
                # 复制目录
                shutil.copytree(path, target_dir)
                
                # 创建 _meta.json
                self._create_meta(target_dir, "local", str(path))
                
                return InstallResult(True, f"从本地安装成功", skill_name, metadata.get('version', ''))
                
            except Exception as e:
                return InstallResult(False, f"读取 SKILL.md 失败: {e}")
        
        elif path.is_file():
            # 假设是 SKILL.md 文件
            if path.name.lower() != "skill.md":
                return InstallResult(False, f"单个文件必须是 SKILL.md")
            
            try:
                content = path.read_text(encoding='utf-8')
                metadata = self._parse_frontmatter(content)
                if not metadata or 'name' not in metadata:
                    return InstallResult(False, "SKILL.md 缺少 name 字段")
                
                skill_name = metadata['name']
                target_dir = self._get_target_dir(skill_name)
                
                # 检查是否已存在
                if target_dir.exists():
                    return InstallResult(False, f"Skill '{skill_name}' 已存在")
                
                target_dir.mkdir(parents=True, exist_ok=True)
                
                # 复制文件
                shutil.copy2(path, target_dir / "SKILL.md")
                
                # 创建 _meta.json
                self._create_meta(target_dir, "local", str(path.parent))
                
                return InstallResult(True, f"从本地安装成功", skill_name, metadata.get('version', ''))
                
            except Exception as e:
                return InstallResult(False, f"安装失败: {e}")
        
        return InstallResult(False, f"未知路径类型: {path}")
    
    async def _install_from_zip(self, data: bytes) -> InstallResult:
        """从 zip 数据安装"""
        import zipfile
        from io import BytesIO
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                zip_path = tmp_path / "skill.zip"
                zip_path.write_bytes(data)
                
                # 解压
                extract_dir = tmp_path / "extracted"
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(extract_dir)
                
                # 查找 skill 目录
                skill_dir = self._find_skill_directory(extract_dir)
                if not skill_dir:
                    return InstallResult(False, "压缩包中未找到有效的 skill")
                
                # 安装
                return await self._install_from_directory(skill_dir)
                
        except Exception as e:
            return InstallResult(False, f"解压失败: {e}")
    
    async def _install_from_tar(self, data: bytes) -> InstallResult:
        """从 tar.gz 数据安装"""
        import tarfile
        from io import BytesIO
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                tar_path = tmp_path / "skill.tar.gz"
                tar_path.write_bytes(data)
                
                # 解压
                extract_dir = tmp_path / "extracted"
                with tarfile.open(tar_path, 'r:gz') as tf:
                    tf.extractall(extract_dir)
                
                # 查找 skill 目录
                skill_dir = self._find_skill_directory(extract_dir)
                if not skill_dir:
                    return InstallResult(False, "压缩包中未找到有效的 skill")
                
                # 安装
                return await self._install_from_directory(skill_dir)
                
        except Exception as e:
            return InstallResult(False, f"解压失败: {e}")
    
    async def _install_from_content(self, content: str) -> InstallResult:
        """从 SKILL.md 内容安装"""
        metadata = self._parse_frontmatter(content)
        if not metadata or 'name' not in metadata:
            return InstallResult(False, "无效的 SKILL.md 文件")
        
        name = metadata['name']
        target_dir = self._get_target_dir(name)
        
        # 检查是否已存在
        if target_dir.exists():
            return InstallResult(False, f"Skill '{name}' 已存在")
        
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        (target_dir / "SKILL.md").write_text(content, encoding='utf-8')
        
        # 创建 _meta.json
        self._create_meta(target_dir, "url", "")
        
        return InstallResult(True, "安装成功", name, metadata.get('version', ''))
    
    async def _install_from_directory(self, source_dir: Path) -> InstallResult:
        """从目录安装"""
        skill_md = source_dir / "SKILL.md"
        if not skill_md.exists():
            return InstallResult(False, "目录中缺少 SKILL.md")
        
        try:
            content = skill_md.read_text(encoding='utf-8')
            metadata = self._parse_frontmatter(content)
            if not metadata or 'name' not in metadata:
                return InstallResult(False, "SKILL.md 缺少 name 字段")
            
            skill_name = metadata['name']
            target_dir = self._get_target_dir(skill_name)
            
            # 检查是否已存在
            if target_dir.exists():
                return InstallResult(False, f"Skill '{skill_name}' 已存在")
            
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # 复制目录内容
            for item in source_dir.iterdir():
                if item.is_dir():
                    shutil.copytree(item, target_dir / item.name)
                else:
                    shutil.copy2(item, target_dir / item.name)
            
            # 创建 _meta.json
            self._create_meta(target_dir, "url", "")
            
            return InstallResult(True, "安装成功", skill_name, metadata.get('version', ''))
            
        except Exception as e:
            return InstallResult(False, f"安装失败: {e}")
    
    def _find_skill_directory(self, root: Path) -> Optional[Path]:
        """在目录中查找包含 SKILL.md 的目录"""
        # 直接检查根目录
        if (root / "SKILL.md").exists():
            return root
        
        # 检查子目录（只检查一层）
        for subdir in root.iterdir():
            if subdir.is_dir() and (subdir / "SKILL.md").exists():
                return subdir
        
        return None
    
    def _get_target_dir(self, skill_name: str) -> Path:
        """获取 skill 目标目录"""
        return self.install_path / skill_name
    
    def _create_meta(self, target_dir: Path, source: str, source_url: str, version: str = ""):
        """创建 _meta.json"""
        meta = {
            "source": source,
            "source_url": source_url,
            "version": version or "1.0.0",
            "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "enabled": True,
        }
        (target_dir / "_meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
    
    def _parse_frontmatter(self, content: str) -> Optional[Dict]:
        """解析 YAML frontmatter"""
        if not content.startswith('---'):
            return None
        
        try:
            _, frontmatter, _ = content.split('---', 2)
            import yaml
            return yaml.safe_load(frontmatter)
        except Exception:
            return None
    
    def validate_skill_directory(self, path: Path) -> Tuple[bool, str]:
        """验证 skill 目录是否有效"""
        path = Path(path)
        
        if not path.exists():
            return False, "路径不存在"
        
        if not path.is_dir():
            return False, "不是目录"
        
        skill_md = path / "SKILL.md"
        if not skill_md.exists():
            return False, "缺少 SKILL.md"
        
        try:
            content = skill_md.read_text(encoding='utf-8')
            metadata = self._parse_frontmatter(content)
            
            if not metadata:
                return False, "SKILL.md 缺少 frontmatter"
            
            if 'name' not in metadata:
                return False, "缺少 name 字段"
            
            if 'description' not in metadata:
                return False, "缺少 description 字段"
            
            return True, metadata['name']
            
        except Exception as e:
            return False, f"读取失败: {e}"


# 全局安装器实例
def get_installer(user_paths: List[str]) -> SkillInstaller:
    """获取安装器实例（使用第一个用户路径）"""
    install_path = Path(user_paths[0]) if user_paths else Path("data/skills")
    return SkillInstaller(install_path)
