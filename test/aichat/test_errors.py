"""infra.errors 单元测试

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_errors.py
"""
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(_PROJECT_ROOT / "hoshino" / "modules" / "aichat" / "aichat"))

from infra.errors import (  # noqa: E402
    AppError,
    LLMAuthError,
    LLMError,
    LLMNetworkError,
    LLMParseError,
    LLMRateLimitedError,
    LLMRequestError,
    LLMTimeoutError,
    LLMUpstreamError,
    Result,
)


class TestErrorHierarchy(unittest.TestCase):
    def test_hierarchy_and_attrs(self):
        err = LLMRateLimitedError("限流", retry_after=1.5)
        self.assertIsInstance(err, LLMError)
        self.assertIsInstance(err, AppError)
        self.assertEqual(err.code, "llm.rate_limited")
        self.assertTrue(err.retryable)
        self.assertEqual(err.status_code, 429)
        self.assertEqual(err.retry_after, 1.5)

    def test_default_retryable(self):
        self.assertFalse(LLMAuthError("x").retryable)
        self.assertFalse(LLMRequestError("x").retryable)
        self.assertFalse(LLMParseError("x").retryable)
        self.assertTrue(LLMNetworkError("x").retryable)
        self.assertTrue(LLMTimeoutError("x").retryable)
        self.assertTrue(LLMUpstreamError("x").retryable)

    def test_str_contains_code(self):
        self.assertIn("llm.auth", str(LLMAuthError("bad key")))
        self.assertIn("bad key", str(LLMAuthError("bad key")))

    def test_cause_kept(self):
        cause = ValueError("root")
        err = LLMNetworkError("wrapped", cause=cause)
        self.assertIs(err.cause, cause)


class TestResult(unittest.TestCase):
    def test_success(self):
        r = Result.success(42)
        self.assertTrue(r.ok)
        self.assertIsNone(r.error)
        self.assertEqual(r.unwrap(), 42)
        self.assertEqual(r.unwrap_or(0), 42)

    def test_success_with_none_value(self):
        r = Result.success(None)
        self.assertTrue(r.ok)
        self.assertIsNone(r.unwrap())

    def test_failure(self):
        err = AppError("boom", code="test.boom")
        r = Result.failure(err)
        self.assertFalse(r.ok)
        self.assertIs(r.error, err)
        self.assertEqual(r.unwrap_or("d"), "d")
        with self.assertRaises(AppError):
            r.unwrap()

    def test_invalid_construction(self):
        with self.assertRaises(ValueError):
            Result()
        with self.assertRaises(ValueError):
            Result(value=1, error=AppError("x", code="x"))


if __name__ == "__main__":
    unittest.main()
