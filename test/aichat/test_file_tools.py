"""read_file 工具测试（路径校验 / 存在性 / 大小上限）

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_file_tools.py
"""
import sys
import tempfile
import unittest
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

import nonebot  # noqa: E402
nonebot.init()

sys.path.insert(0, str(_PROJECT_ROOT))

from hoshino.modules.aichat.aichat.tools.builtin import file_tools  # noqa: E402
from hoshino.modules.aichat.aichat.tools.builtin import store_images  # noqa: E402


class TestReadFile(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        (root / "ok.txt").write_text("你好，世界", encoding="utf-8")
        (root / "big.bin").write_bytes(b"x" * (file_tools.MAX_READ_SIZE + 1))
        # 重定向允许根目录到临时目录（_check_path 引用 store_images 模块级常量）
        self._old_root = store_images.ALLOWED_ROOT
        store_images.ALLOWED_ROOT = root.resolve()

    def tearDown(self):
        store_images.ALLOWED_ROOT = self._old_root
        self._tmp.cleanup()

    async def _call(self, path: str):
        return await file_tools.read_file(path)

    async def test_read_existing_file(self):
        result = await self._call("ok.txt")
        self.assertTrue(result["success"], result)
        self.assertEqual(result["content"], "你好，世界")
        self.assertTrue(result["metadata"]["exists"])

    async def test_read_missing_file(self):
        result = await self._call("nope.txt")
        self.assertTrue(result["success"], result)
        self.assertFalse(result["metadata"]["exists"])
        self.assertEqual(result["content"], "")

    async def test_absolute_path_rejected(self):
        result = await self._call("/etc/passwd")
        self.assertFalse(result["success"], result)

    async def test_path_traversal_rejected(self):
        result = await self._call("../outside.txt")
        self.assertFalse(result["success"], result)

    async def test_escape_root_rejected(self):
        # 即使不含 ..，resolve 后越出根目录也应拒绝（如通过嵌套符号链接）
        result = await self._call("ok.txt/../../etc/passwd")
        self.assertFalse(result["success"], result)

    async def test_oversized_file_rejected(self):
        result = await self._call("big.bin")
        self.assertFalse(result["success"], result)
        self.assertIn("过大", result["content"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
