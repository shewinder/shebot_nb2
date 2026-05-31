"""
北洋园 (TJUPT) 搜索脚本测试

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/ptdownload/test_tjupt.py
"""
import os
import sys
import unittest
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

sys.path.insert(0, str(_PROJECT_ROOT / "hoshino" / "modules" / "aichat" / "aichat" / "skills" / "ptdownload" / "scripts"))
import search_tjupt as tjupt


class TestLiveAPI(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("PT_TJUPT_COOKIE"), "PT_TJUPT_COOKIE 未配置")
    def test_search(self):
        import asyncio
        result = asyncio.run(tjupt.search("test"))
        self.assertTrue(result.get("success"), f"失败: {result.get('error')}")
        self.assertGreaterEqual(len(result.get("results", [])), 0)
        print(f"  [ok] {result['count']} 个结果")


if __name__ == "__main__":
    unittest.main(verbosity=2)
