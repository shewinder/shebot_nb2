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

from hoshino.modules.aichat.aichat._image_store_core import ImageStoreCore  # noqa: E402
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

        # 模拟 chat.py 的锚定插入：图片的独立标识符消息在历史中
        s.add_raw_message({"role": "user", "content": "用户发送了图片：<user_image_1>（png 100x100，已保存）"})

        msgs = await s._build_messages_for_chat(None)

        # 持久历史不被污染（构建不修改历史、不附加任何动态清单）
        self.assertEqual(s.messages[0]["content"], "看这张图")
        self.assertEqual(s.messages[1]["content"], "好的")
        self.assertEqual(s.messages[2]["content"], "用户发送了图片：<user_image_1>（png 100x100，已保存）")
        self.assertNotIn("【当前可用图片】", str(s.messages))

        # 构建结果与历史一致（锚定消息随历史进入 API 消息）
        joined = " ".join(str(m.get("content")) for m in msgs)
        self.assertIn("用户发送了图片：<user_image_1>", joined)
        self.assertNotIn("【当前可用图片】", joined)


class _FakeMediaEntry:
    def __init__(self, fmt, width=None, height=None, size_bytes=0):
        self.format = fmt
        self.width = width
        self.height = height
        self.size_bytes = size_bytes


class TestMediaAnchorMerge(unittest.TestCase):
    """用户媒体锚定：一次用户消息合并为一条锚定消息（与用户行为一致）"""

    class _FakeStore:
        def __init__(self, entries):
            self.entries = entries

        def get(self, identifier):
            return self.entries.get(identifier)

    def _make_session(self, images=None, videos=None):
        session = SimpleNamespace(
            _image_store=self._FakeStore(images or {}),
            _video_store=self._FakeStore(videos or {}),
        )
        return session

    def test_single_image_keeps_meta(self):
        from hoshino.modules.aichat.aichat.chat import _build_media_anchor_message

        s = self._make_session(images={"<user_image_1>": _FakeMediaEntry("png", 100, 100)})
        text = _build_media_anchor_message(s, ["<user_image_1>"], [])
        self.assertEqual(text, "用户发送了图片：<user_image_1>（png 100x100，已保存）")

    def test_multiple_images_merge_into_one_anchor(self):
        from hoshino.modules.aichat.aichat.chat import _build_media_anchor_message

        s = self._make_session(
            images={
                "<user_image_1>": _FakeMediaEntry("png"),
                "<user_image_2>": _FakeMediaEntry("jpg"),
            }
        )
        text = _build_media_anchor_message(s, ["<user_image_1>", "<user_image_2>"], [])
        self.assertEqual(text, "用户发送了 2 张图片：<user_image_1>、<user_image_2>（已保存）")

    def test_mixed_media_single_anchor(self):
        from hoshino.modules.aichat.aichat.chat import _build_media_anchor_message

        s = self._make_session(
            images={
                "<user_image_1>": _FakeMediaEntry("png"),
                "<user_image_2>": _FakeMediaEntry("jpg"),
            },
            videos={"<user_video_1>": _FakeMediaEntry("mp4", size_bytes=2048)},
        )
        text = _build_media_anchor_message(s, ["<user_image_1>", "<user_image_2>"], ["<user_video_1>"])
        self.assertEqual(
            text,
            "用户发送了 2 张图片：<user_image_1>、<user_image_2>（已保存）；"
            "用户发送了视频：<user_video_1>（mp4 2KB，已保存）",
        )

    def test_no_media_returns_none(self):
        from hoshino.modules.aichat.aichat.chat import _build_media_anchor_message

        s = self._make_session()
        self.assertIsNone(_build_media_anchor_message(s, [], []))


class TestImageStoreCore(unittest.TestCase):
    def test_get_data_url_refreshes_meta_written_by_another_instance(self):
        """跨实例写入后，已有实例首次读取即可获取图像"""
        tmp = tempfile.TemporaryDirectory()
        old_base = ImageStoreCore.BASE_DIR
        ImageStoreCore.BASE_DIR = Path(tmp.name)
        try:
            reader = ImageStoreCore("cross_process_sess")
            writer = ImageStoreCore("cross_process_sess")
            png = b"\x89PNG\r\n\x1a\n" + b"x" * 16

            entry = writer.store_bytes(png, "ai")

            self.assertIsNotNone(reader.get_data_url(entry.identifier))
        finally:
            ImageStoreCore.BASE_DIR = old_base
            tmp.cleanup()

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


class TestVideoStoreCore(unittest.TestCase):
    def test_lazy_dir_user_source_and_clear(self):
        """视频存储与图片对齐：惰性建目录、user 源标识符、clear 删目录"""
        from hoshino.modules.aichat.aichat._video_store_core import BASE_DIR, VideoStoreCore

        tmp = tempfile.TemporaryDirectory()
        old_base = BASE_DIR
        BASE_DIR = Path(tmp.name)
        try:
            store = VideoStoreCore("vid_sess")
            self.assertFalse(store._dir.exists())  # 构造零目录

            # user 源：标识符 <user_video_1>，url 记录
            entry = store.store_bytes(b"\x00video", "user", "mp4", url="https://example.com/a.mp4")
            self.assertEqual(entry.identifier, "<user_video_1>")
            self.assertEqual(entry.url, "https://example.com/a.mp4")
            self.assertTrue(store._dir.exists())

            # ai 源标识符独立编号
            entry2 = store.store_bytes(b"\x00video2", "ai", "mp4")
            self.assertEqual(entry2.identifier, "<ai_video_1>")

            # clear：内容与目录一并消失
            store.clear()
            self.assertFalse(store._dir.exists())
            self.assertEqual(store.list_all(), [])
        finally:
            BASE_DIR = old_base
            tmp.cleanup()


class TestVideoSessionMethods(unittest.IsolatedAsyncioTestCase):
    async def test_store_user_video_is_async(self):
        """回归：store_user_video 为 async（曾被同步实现 + await 调用导致崩溃，
        表现为转发视频已存储但对话未进入、历史丢失）"""
        from hoshino.modules.aichat.aichat._video_store_core import BASE_DIR

        tmp = tempfile.TemporaryDirectory()
        old_base = BASE_DIR
        BASE_DIR = Path(tmp.name)
        try:
            s = Session("vid_method_1", 1)
            ident = await s.store_user_video(b"\x00v", url="https://example.com/v.mp4")
            self.assertEqual(ident, "<user_video_1>")
            # AI 侧同理
            ident2 = await s.store_ai_video_bytes(b"\x00v2")
            self.assertEqual(ident2, "<ai_video_1>")
        finally:
            BASE_DIR = old_base
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
