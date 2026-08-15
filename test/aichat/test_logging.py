"""infra.logging 单元测试（脱敏与日志上下文）

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_logging.py
"""
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(_PROJECT_ROOT / "hoshino" / "modules" / "aichat" / "aichat"))

from infra.logging import log_context, log_tag, sanitize, sanitize_text  # noqa: E402


class TestSanitize(unittest.TestCase):
    def test_base64_blob_replaced(self):
        blob = "data:image/png;base64," + "A" * 200
        out = sanitize_text(f"图片: {blob} 结束")
        self.assertNotIn("AAAA", out)
        self.assertIn("[base64数据已省略]", out)
        self.assertIn("结束", out)

    def test_short_base64_kept(self):
        short = "data:image/png;base64," + "B" * 40
        out = sanitize_text(short)
        self.assertIn("B" * 40, out)

    def test_truncate(self):
        out = sanitize_text("x" * 5000, max_len=100)
        self.assertIn("截断", out)
        self.assertLess(len(out), 100 + 40)

    def test_recursive(self):
        data = {"a": ["data:image/png;base64," + "C" * 200], "b": 123, "c": ({"d": "ok"},)}
        out = sanitize(data)
        self.assertEqual(out["b"], 123)
        self.assertNotIn("CCCC", out["a"][0])
        self.assertEqual(out["c"][0]["d"], "ok")


class TestLogContext(unittest.TestCase):
    def test_empty_tag(self):
        self.assertEqual(log_tag(), "")

    def test_tag_within_context(self):
        with log_context(session="group_1_user_2", agent="main"):
            self.assertEqual(log_tag(), "[session=group_1_user_2][agent=main]")
        self.assertEqual(log_tag(), "")

    def test_nested_context_restores(self):
        with log_context(session="outer"):
            with log_context(agent="inner"):
                self.assertEqual(log_tag(), "[agent=inner]")
            self.assertEqual(log_tag(), "[session=outer]")


if __name__ == "__main__":
    unittest.main()
