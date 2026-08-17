"""记忆系统测试（全局记忆 + 用户记忆 + 注入截断 + 权限）

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_memory.py
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

import nonebot  # noqa: E402
nonebot.init()

sys.path.insert(0, str(_PROJECT_ROOT))

from hoshino.modules.aichat.aichat.memory import GLOBAL_MEMORY_KEY, memory_store  # noqa: E402
from hoshino.modules.aichat.aichat.session import Session  # noqa: E402
from hoshino.modules.aichat.aichat.tools import permission  # noqa: E402
from hoshino.modules.aichat.aichat.tools.access import get_available_tools  # noqa: E402


class TestGlobalMemory(unittest.IsolatedAsyncioTestCase):
    async def test_write_read_clear(self):
        # 独立临时目录，不碰生产数据
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        old_dir = memory_store._data_dir
        memory_store._data_dir = Path(tmp.name)
        try:
            # 空模板 → 注入为空
            self.assertEqual(await memory_store.get_global_inject_text(1500), "")

            ok = await memory_store.write_global("# 全局记忆\n\n## 公共约定\n\n- 群内禁广告\n")
            self.assertTrue(ok)
            content = await memory_store.read_global()
            self.assertIn("禁广告", content)

            injected = await memory_store.get_global_inject_text(1500)
            self.assertIn("禁广告", injected)

            ok = await memory_store.clear_global()
            self.assertTrue(ok)
            self.assertEqual(await memory_store.get_global_inject_text(1500), "")
        finally:
            memory_store._data_dir = old_dir
            tmp.cleanup()

    async def test_user_memory_isolated_from_global(self):
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        old_dir = memory_store._data_dir
        memory_store._data_dir = Path(tmp.name)
        try:
            await memory_store.write_global("全局内容")
            await memory_store.write(1, "# 用户记忆\n\n## 事实\n\n- 用户A喜欢猫\n")
            # 全局文件与用户文件互不干扰
            self.assertIn("全局内容", await memory_store.read_global())
            self.assertIn("猫", await memory_store.read(1))
            self.assertNotIn("全局内容", await memory_store.read(1))
        finally:
            memory_store._data_dir = old_dir
            tmp.cleanup()


class TestTruncateBothEnds(unittest.TestCase):
    def test_short_content_unchanged(self):
        content = "abc" * 100
        self.assertEqual(memory_store._truncate_both_ends(content, 10000), content)

    def test_long_content_keeps_both_ends(self):
        head = "## 事实\n" + "A" * 3000
        tail = "最新事件\n" + "B" * 3000
        content = head + "\n" + tail
        out = memory_store._truncate_both_ends(content, 2000)
        self.assertLess(len(out), 2200)
        self.assertIn("## 事实", out)       # 头部结构保留
        self.assertIn("B" * 500, out)      # 尾部最新内容保留
        self.assertIn("...", out)


class TestGlobalMemoryPermission(unittest.IsolatedAsyncioTestCase):
    async def test_write_global_superuser_only(self):
        with patch.object(permission, "_get_superusers", return_value={10001}):
            normal = Session("mem_perm_n_1", 99999)
            su = Session("mem_perm_s_1", 10001)
            names_normal = {t["function"]["name"] for t in await get_available_tools(normal)}
            names_su = {t["function"]["name"] for t in await get_available_tools(su)}
        self.assertNotIn("write_global_memory", names_normal)
        self.assertIn("write_global_memory", names_su)
        self.assertIn("read_global_memory", names_normal)  # 读对所有人开放


if __name__ == "__main__":
    unittest.main()
