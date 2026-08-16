"""infra.metrics 单元测试

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_metrics.py
"""
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(_PROJECT_ROOT / "hoshino" / "modules" / "aichat" / "aichat"))

from infra.metrics import Metrics  # noqa: E402


class TestMetrics(unittest.TestCase):
    def setUp(self):
        self.m = Metrics()

    def test_llm_call_recording(self):
        self.m.record_llm_call(120.5, {"prompt_tokens": 10, "completion_tokens": 5})
        self.m.record_llm_call(220.5, None)
        snap = self.m.snapshot()
        self.assertEqual(snap["llm_calls"], 2)
        self.assertEqual(snap["llm_prompt_tokens"], 10)
        self.assertEqual(snap["llm_completion_tokens"], 5)
        self.assertAlmostEqual(snap["llm_avg_latency_ms"], 170.5)
        self.assertEqual(snap["llm_max_latency_ms"], 220.5)

    def test_llm_error_recording(self):
        self.m.record_llm_error("llm.rate_limited")
        self.m.record_llm_error("llm.rate_limited")
        self.m.record_llm_error("llm.timeout")
        snap = self.m.snapshot()
        self.assertEqual(snap["llm_calls"], 3)
        self.assertEqual(snap["llm_error_codes"], {"llm.rate_limited": 2, "llm.timeout": 1})

    def test_tool_recording(self):
        self.m.record_tool_call(50.0)
        self.m.record_tool_call(150.0)
        self.m.record_tool_timeout()
        snap = self.m.snapshot()
        self.assertEqual(snap["tool_calls"], 2)
        self.assertEqual(snap["tool_timeouts"], 1)
        self.assertEqual(snap["tool_avg_latency_ms"], 100.0)

    def test_empty_snapshot(self):
        snap = self.m.snapshot()
        self.assertEqual(snap["llm_calls"], 0)
        self.assertEqual(snap["llm_avg_latency_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()
