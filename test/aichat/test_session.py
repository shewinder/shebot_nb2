"""session 单元测试（回溯 + dispose 行为）

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_session.py
"""
import sys
import unittest
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

import nonebot  # noqa: E402
nonebot.init()

sys.path.insert(0, str(_PROJECT_ROOT))

from hoshino.modules.aichat.aichat.session import Session, session_manager  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
