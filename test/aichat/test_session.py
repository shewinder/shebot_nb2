"""session 单元测试（回溯 / dispose / 历史非破坏性构建 / 图库锁与清理）

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_session.py
"""
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

import nonebot  # noqa: E402
nonebot.init()

sys.path.insert(0, str(_PROJECT_ROOT))

from hoshino.modules.aichat.aichat.session import Session, session_manager  # noqa: E402


class FakeImageStore:
    """内存假图库（仅 build_image_list_prompt 需要 list_all）"""

    def __init__(self, list_entries=None):
        self.list_entries = list_entries or []

    def list_all(self):
        return self.list_entries


class TestRollback(unittest.TestCase):
    def setUp(self):
        self.session = Session("rollback_test_1", 1)

    def _fill(self, rounds: int):
        for i in range(rounds):
            self.session.add_message("user", f"u{i}")
            self.session.add_message("assistant", f"a{i}")
            # 模拟中间工具消息
            self.session.add_raw_message({"role": "tool", "content": f"t{i}"})

    def test_rollback_n_rounds(self):
        self._fill(5)
        deleted, actual = self.session.rollback_messages(2)
        self.assertEqual(actual, 2)
        # 2 轮 × (user + assistant + tool) = 6 条
        self.assertEqual(deleted, 6)
        self.assertEqual(len(self.session.messages), 3 * 3)
        self.assertEqual(self.session.messages[-1]["content"], "t2")

    def test_rollback_more_than_history(self):
        self._fill(2)
        deleted, actual = self.session.rollback_messages(10)
        self.assertEqual(actual, 2)
        self.assertEqual(len(self.session.messages), 0)
        self.assertGreater(deleted, 0)

    def test_rollback_empty(self):
        deleted, actual = self.session.rollback_messages(1)
        self.assertEqual((deleted, actual), (0, 0))


class TestDispose(unittest.TestCase):
    def test_dispose_removes_from_registry_via_manager(self):
        s = session_manager.create_session(777, 888)
        self.assertIsNotNone(session_manager.get_session(777, 888))
        session_manager.clear_session(777, 888)
        self.assertIsNone(session_manager.get_session(777, 888))


class TestBuildMessagesNonMutation(unittest.IsolatedAsyncioTestCase):
    async def test_image_prompt_not_appended_to_history(self):
        s = Session("build_test_1", 1)
        s.add_message("user", "看这张图")
        s.add_message("assistant", "好的")
        img = SimpleNamespace(
            identifier="<user_image_1>", source="user", format="png",
            width=100, height=100, url=None,
        )
        s._image_store = FakeImageStore([img])

        msgs = await s._build_messages_for_chat(None)

        # 持久历史不被污染
        self.assertEqual(s.messages[0]["content"], "看这张图")
        self.assertEqual(s.messages[1]["content"], "好的")
        self.assertNotIn("【当前可用图片】", str(s.messages))

        # API 消息副本中附加了图片列表提示
        joined = " ".join(str(m.get("content")) for m in msgs)
        self.assertIn("【当前可用图片】", joined)


class TestImageStoreCore(unittest.TestCase):
    def test_store_cleanup_and_concurrent_lock(self):
        from hoshino.modules.aichat.aichat._image_store_core import ImageStoreCore

        tmp = tempfile.TemporaryDirectory()
        old_base = ImageStoreCore.BASE_DIR
        ImageStoreCore.BASE_DIR = Path(tmp.name)
        try:
            store = ImageStoreCore("sess_x")
            png = b"\x89PNG\r\n\x1a\n" + b"x" * 16

            # 顺序存储：编号唯一、清理上限生效
            store.store_bytes(png, "ai")
            store.store_bytes(png, "ai")
            store.store_bytes(png, "ai")
            store.cleanup(max_images=2)
            self.assertEqual(len(store.list_all()), 2)

            # 并发存储：持锁串行化，序号不重复
            threads = [threading.Thread(target=store.store_bytes, args=(png, "ai")) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            identifiers = [e.identifier for e in store.list_all()]
            self.assertEqual(len(identifiers), len(set(identifiers)))

            store.clear()
            self.assertEqual(len(store.list_all()), 0)
        finally:
            ImageStoreCore.BASE_DIR = old_base
            tmp.cleanup()

    def test_lazy_dir_creation_and_clear_removes_dir(self):
        """回归：会话创建不再急切建目录（修复空目录堆积）；clear 后目录消失"""
        from hoshino.modules.aichat.aichat._image_store_core import ImageStoreCore

        tmp = tempfile.TemporaryDirectory()
        old_base = ImageStoreCore.BASE_DIR
        ImageStoreCore.BASE_DIR = Path(tmp.name)
        try:
            # 1. 仅构造（无存储）→ 不产生目录
            store = ImageStoreCore("lazy_sess")
            self.assertFalse(store._dir.exists())

            # 2. 存储 → 目录按需创建
            store.store_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 16, "ai")
            self.assertTrue(store._dir.exists())
            self.assertTrue(store._dir.is_dir())

            # 3. clear → 目录一并删除
            store.clear()
            self.assertFalse(store._dir.exists())
        finally:
            ImageStoreCore.BASE_DIR = old_base
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
