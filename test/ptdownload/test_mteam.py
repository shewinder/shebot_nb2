"""
M-Team 搜索脚本测试

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/ptdownload/test_mteam.py
"""
import os
import sys
import unittest
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

sys.path.insert(0, str(_PROJECT_ROOT / "hoshino" / "modules" / "aichat" / "aichat" / "skills" / "ptdownload" / "scripts"))
import search_mteam as m


class TestLiveAPI(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("PT_MSTEAM_AUTH"), "PT_MSTEAM_AUTH 未配置")
    def test_search(self):
        import asyncio
        result = asyncio.run(m.search("test", size=2))
        self.assertTrue(result.get("success"), f"失败: {result.get('error')}")
        self.assertGreater(len(result.get("results", [])), 0)
        print(f"  [ok] {result['count']} 个结果")

    @unittest.skipUnless(os.environ.get("PT_MSTEAM_AUTH"), "PT_MSTEAM_AUTH 未配置")
    def test_search_free_only(self):
        import asyncio
        result = asyncio.run(m.search("test", free_only=True, size=50))
        self.assertTrue(result.get("success"), f"失败: {result.get('error')}")
        for r in result.get("results", []):
            self.assertEqual(r["discount"], "FREE")
        print(f"  [ok] {result['count']} 个免费种")


if __name__ == "__main__":
    unittest.main(verbosity=2)
