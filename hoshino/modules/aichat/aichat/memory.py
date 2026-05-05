"""用户记忆存储模块

使用 Markdown 纯文本文件为每个用户维护一份记忆笔记。
AI 通过 read_memory / write_memory 工具自主读写，实现自然语言级别的记忆管理。
"""
import asyncio
from pathlib import Path
from typing import Optional
from loguru import logger

from hoshino import userdata_dir


class MemoryStore:
    """用户记忆存储器

    每个用户对应一个 Markdown 文件：data/aichat/memories/{user_id}.md
    使用按用户分片的 asyncio.Lock 保证并发安全。
    """

    def __init__(self) -> None:
        self._data_dir: Path = userdata_dir.joinpath('aichat', 'memories')
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file_locks: dict[int, asyncio.Lock] = {}

    def _get_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._file_locks:
            self._file_locks[user_id] = asyncio.Lock()
        return self._file_locks[user_id]

    def _get_file_path(self, user_id: int) -> Path:
        return self._data_dir / f"{user_id}.md"

    @staticmethod
    def default_template() -> str:
        return (
            "# 用户记忆\n\n"
            "## 偏好\n\n"
            "## 事实\n\n"
            "## 计划\n\n"
            "## 其他\n"
        )

    async def read(self, user_id: int) -> str:
        """读取用户记忆文件内容

        文件不存在时返回默认模板。
        """
        async with self._get_lock(user_id):
            file_path = self._get_file_path(user_id)
            if not file_path.exists():
                return self.default_template()
            try:
                return file_path.read_text(encoding='utf-8')
            except Exception as e:
                logger.exception(f"读取记忆失败 user_id={user_id}: {e}")
                return self.default_template()

    async def write(self, user_id: int, content: str) -> bool:
        """覆盖写入用户记忆文件"""
        async with self._get_lock(user_id):
            file_path = self._get_file_path(user_id)
            try:
                file_path.write_text(content, encoding='utf-8')
                return True
            except Exception as e:
                logger.exception(f"写入记忆失败 user_id={user_id}: {e}")
                return False

    async def append(self, user_id: int, text: str) -> bool:
        """追加内容到记忆文件末尾

        用于用户手动「记住」命令。以 Markdown 列表项格式追加。
        """
        async with self._get_lock(user_id):
            file_path = self._get_file_path(user_id)
            if file_path.exists():
                content = file_path.read_text(encoding='utf-8')
            else:
                content = self.default_template()

            if not content.endswith('\n'):
                content += '\n'
            content += f"\n- {text}\n"

            try:
                file_path.write_text(content, encoding='utf-8')
                return True
            except Exception as e:
                logger.exception(f"追加记忆失败 user_id={user_id}: {e}")
                return False

    async def clear(self, user_id: int) -> bool:
        """清空用户记忆，重置为默认模板"""
        async with self._get_lock(user_id):
            file_path = self._get_file_path(user_id)
            if not file_path.exists():
                return False
            try:
                file_path.write_text(self.default_template(), encoding='utf-8')
                return True
            except Exception as e:
                logger.exception(f"清空记忆失败 user_id={user_id}: {e}")
                return False

    async def get_inject_text(self, user_id: int, max_length: int = 1500) -> str:
        """获取用于注入 system prompt 的记忆文本

        如果记忆文件为空或仅有默认模板，返回空字符串。
        超长时按段落边界截断，并添加省略提示。
        """
        content = await self.read(user_id)
        if content.strip() == self.default_template().strip():
            return ""

        if len(content) <= max_length:
            return content

        # 在段落边界截断，避免截断到标题中间
        truncated = content[:max_length]
        last_newline = truncated.rfind('\n')
        if last_newline > max_length * 0.7:
            truncated = truncated[:last_newline]

        return truncated + "\n\n...（更多记忆已省略）"


memory_store = MemoryStore()
