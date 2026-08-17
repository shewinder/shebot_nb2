"""记忆存储模块

两层记忆（用户决策：区分全局记忆与用户记忆）：
- 全局记忆：memories/global.md，bot 级公共知识，所有会话注入（超管维护）
- 用户记忆：memories/{user_id}.md，个人事实，仅本人会话注入
AI 通过 read_memory/write_memory/read_global_memory/write_global_memory
工具自主读写，实现自然语言级别的记忆管理。
"""
import asyncio
from pathlib import Path
from typing import Optional
from loguru import logger

from hoshino import userdata_dir

# 全局记忆文件名（字符串键，与纯数字 user_id 天然不冲突）
GLOBAL_MEMORY_KEY = "global"


class MemoryStore:
    """记忆存储器

    全局记忆 + 每用户记忆，均为 Markdown 文件；
    按 key 分片加锁保证并发安全。
    """

    def __init__(self) -> None:
        self._data_dir: Path = userdata_dir.joinpath('aichat', 'memories')
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file_locks: dict[object, asyncio.Lock] = {}

    def _get_lock(self, key: object) -> asyncio.Lock:
        if key not in self._file_locks:
            self._file_locks[key] = asyncio.Lock()
        return self._file_locks[key]

    def _get_file_path(self, key: object) -> Path:
        return self._data_dir / f"{key}.md"

    @staticmethod
    def default_template() -> str:
        return (
            "# 用户记忆\n\n"
            "## 偏好\n\n"
            "## 事实\n\n"
            "## 计划\n\n"
            "## 其他\n"
        )

    @staticmethod
    def global_template() -> str:
        return (
            "# 全局记忆\n\n"
            "## 公共约定\n\n"
            "## 运营知识\n\n"
            "## 其他\n"
        )

    @staticmethod
    def _truncate_both_ends(content: str, max_length: int) -> str:
        """超长时保留头尾（段落边界对齐）：头部保结构、尾部保最新内容"""
        if len(content) <= max_length:
            return content
        head_len = int(max_length * 0.6)
        tail_len = max(50, max_length - head_len - 8)
        head = content[:head_len]
        cut = head.rfind("\n")
        if cut > head_len * 0.5:
            head = head[:cut]
        tail = content[-tail_len:]
        cut = tail.find("\n")
        if 0 < cut < tail_len * 0.5:
            tail = tail[cut + 1:]
        return head + "\n...\n" + tail

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
        """获取用于注入 system prompt 的用户记忆文本

        如果记忆文件为空或仅有默认模板，返回空字符串。
        超长时保留头尾（头部保结构、尾部保最新）。
        """
        content = await self.read(user_id)
        if content.strip() == self.default_template().strip():
            return ""
        return self._truncate_both_ends(content, max_length)

    # ========== 全局记忆 ==========

    async def read_global(self) -> str:
        """读取全局记忆文件内容；文件不存在时返回全局模板"""
        async with self._get_lock(GLOBAL_MEMORY_KEY):
            file_path = self._get_file_path(GLOBAL_MEMORY_KEY)
            if not file_path.exists():
                return self.global_template()
            try:
                return file_path.read_text(encoding='utf-8')
            except Exception as e:
                logger.exception(f"读取全局记忆失败: {e}")
                return self.global_template()

    async def write_global(self, content: str) -> bool:
        """覆盖写入全局记忆文件"""
        async with self._get_lock(GLOBAL_MEMORY_KEY):
            file_path = self._get_file_path(GLOBAL_MEMORY_KEY)
            try:
                file_path.write_text(content, encoding='utf-8')
                return True
            except Exception as e:
                logger.exception(f"写入全局记忆失败: {e}")
                return False

    async def clear_global(self) -> bool:
        """清空全局记忆，重置为默认模板"""
        async with self._get_lock(GLOBAL_MEMORY_KEY):
            file_path = self._get_file_path(GLOBAL_MEMORY_KEY)
            if not file_path.exists():
                return False
            try:
                file_path.write_text(self.global_template(), encoding='utf-8')
                return True
            except Exception as e:
                logger.exception(f"清空全局记忆失败: {e}")
                return False

    async def get_global_inject_text(self, max_length: int = 1500) -> str:
        """获取用于注入的全局记忆文本；空模板返回空字符串"""
        content = await self.read_global()
        if content.strip() == self.global_template().strip():
            return ""
        return self._truncate_both_ends(content, max_length)


memory_store = MemoryStore()
