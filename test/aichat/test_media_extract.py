"""媒体提取测试（转发消息 CQ 字符串/段列表解析，静默故障修复回归）

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_media_extract.py
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

from hoshino.util.message_util import _extract_media_from_content  # noqa: E402


class TestExtractMediaFromContent(unittest.TestCase):
    def test_cq_string_with_url(self):
        content = "[CQ:image,file=1.jpg,url=https://a.com/1.jpg] 文字 [CQ:video,file=2.mp4,url=https://b.com/2.mp4]"
        segs = _extract_media_from_content(content)
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0], {"type": "image", "url": "https://a.com/1.jpg"})
        self.assertEqual(segs[1], {"type": "video", "url": "https://b.com/2.mp4"})

    def test_cq_string_missing_url_skipped(self):
        content = "[CQ:image,file=1.jpg] [CQ:video,file=2.mp4,url=https://b.com/2.mp4]"
        segs = _extract_media_from_content(content)
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0]["type"], "video")

    def test_segment_list(self):
        content = [
            {"type": "image", "data": {"file": "1.jpg", "url": "https://a.com/1.jpg"}},
            {"type": "video", "data": {"file": "2.mp4", "url": "https://b.com/2.mp4"}},
            {"type": "text", "data": {"text": "hi"}},
        ]
        segs = _extract_media_from_content(content)
        self.assertEqual(len(segs), 2)

    def test_segment_list_missing_url_skipped(self):
        content = [{"type": "image", "data": {"file": "1.jpg"}}]
        segs = _extract_media_from_content(content)
        self.assertEqual(segs, [])

    def test_plain_text_no_media(self):
        self.assertEqual(_extract_media_from_content("就是普通文字"), [])


if __name__ == "__main__":
    unittest.main()
