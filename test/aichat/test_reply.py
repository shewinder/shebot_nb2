"""reply 管道单元测试（build_reply 解析逻辑）

覆盖：保序、空白容错、缺失标识符降级、消息内去重、会话级去重、
session=None 字面降级、@ 解析、auto_attach 兜底补发。

需要 nonebot.init()（reply.py 依赖 hoshino 的 Message 等）。

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_reply.py
"""
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

import nonebot  # noqa: E402
nonebot.init()

sys.path.insert(0, str(_PROJECT_ROOT))

from hoshino.modules.aichat.aichat.reply import build_reply  # noqa: E402
from hoshino.modules.aichat.aichat.session import Session  # noqa: E402


class FakeImageStore:
    def __init__(self, entries=None, list_entries=None):
        self.entries = entries or {}
        self.list_entries = list_entries or []

    def get(self, identifier):
        if identifier not in self.entries:
            return None
        return SimpleNamespace(identifier=identifier, file_path=Path("x.png"))

    def list_all(self):
        return self.list_entries

    def clear(self):
        pass


class TestBuildReply(unittest.IsolatedAsyncioTestCase):
    def _session_with(self, entries=None, list_entries=None):
        s = Session("reply_test_1", 1)
        s._image_store = FakeImageStore(entries, list_entries)
        return s

    async def test_order_preserved(self):
        s = self._session_with({"<ai_image_1>": {}})
        parts = await build_reply("前<ai_image_1>后", s)
        self.assertEqual([p.kind for p in parts], ["text", "image", "text"])
        self.assertEqual(parts[0].text, "前")
        self.assertEqual(parts[1].identifier, "<ai_image_1>")
        self.assertEqual(parts[2].text, "后")

    async def test_whitespace_tolerance(self):
        s = self._session_with({"<ai_image_1>": {}})
        parts = await build_reply("图 < ai_image_1 > 完", s)
        self.assertEqual([p.kind for p in parts], ["text", "image", "text"])

    async def test_missing_identifier_literal(self):
        s = self._session_with({})
        parts = await build_reply("看 <ai_image_99>", s)
        kinds = [p.kind for p in parts]
        self.assertEqual(kinds, ["text", "text"])
        self.assertIn("<ai_image_99>", parts[1].text)

    async def test_duplicate_dedup(self):
        s = self._session_with({"<ai_image_1>": {}})
        parts = await build_reply("a<ai_image_1>b<ai_image_1>", s)
        images = [p for p in parts if p.kind == "image"]
        self.assertEqual(len(images), 1)

    async def test_turn_dedup(self):
        s = self._session_with({"<ai_image_1>": {}})
        s._turn_sent_images.add("<ai_image_1>")
        parts = await build_reply("a<ai_image_1>", s)
        self.assertNotIn("image", [p.kind for p in parts])

    async def test_session_none_literal(self):
        parts = await build_reply("图<ai_image_1>", None)
        self.assertTrue(all(p.kind == "text" for p in parts))
        self.assertIn("<ai_image_1>", "".join(p.text for p in parts))

    async def test_at_token(self):
        s = self._session_with({})
        parts = await build_reply("<@12345>你好", s)
        self.assertEqual(parts[0].kind, "at")
        self.assertEqual(parts[0].qq_id, 12345)
        self.assertEqual(parts[1].text, "你好")

    async def test_short_digits_not_treated_as_at(self):
        """3 位数字不是合法 QQ 号，应保持字面文本"""
        s = self._session_with({})
        parts = await build_reply("<@123>你好", s)
        self.assertTrue(all(p.kind == "text" for p in parts))
        self.assertIn("<@123>", parts[0].text)

    async def test_auto_attach(self):
        s = self._session_with(
            {"<ai_image_2>": {}},
            [SimpleNamespace(source="ai", identifier="<ai_image_2>", created_at=time.time())],
        )
        s.last_user_msg_at = time.time() - 1
        parts = await build_reply("无引用", s)
        images = [p for p in parts if p.kind == "image"]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].identifier, "<ai_image_2>")

    async def test_auto_attach_skips_old_and_user_source(self):
        s = self._session_with(
            {},
            [
                SimpleNamespace(source="ai", identifier="<ai_image_1>", created_at=time.time() - 100),
                SimpleNamespace(source="user", identifier="<user_image_1>", created_at=time.time()),
            ],
        )
        s.last_user_msg_at = time.time() - 1
        parts = await build_reply("无引用", s)
        self.assertEqual([p for p in parts if p.kind == "image"], [])


if __name__ == "__main__":
    unittest.main()
