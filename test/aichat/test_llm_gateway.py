"""infra.llm_gateway 单元测试（httpx.MockTransport，无真实网络）

覆盖：成功解析、tool_calls、429 重试（尊重 Retry-After）、重试耗尽、
401 不重试、5xx 重试、超时分类、错误体脱敏、非法响应解析。

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_llm_gateway.py
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(_PROJECT_ROOT / "hoshino" / "modules" / "aichat" / "aichat"))

from infra.errors import (  # noqa: E402
    LLMAuthError,
    LLMNetworkError,
    LLMParseError,
    LLMRateLimitedError,
    LLMTimeoutError,
    LLMUpstreamError,
)
from infra.llm_gateway import LLMGateway  # noqa: E402

_MSGS = [{"role": "user", "content": "hi"}]


def _make_gateway(handler, max_retries: int = 2) -> LLMGateway:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return LLMGateway("https://api.test", "sk-test", client=client, max_retries=max_retries)


def _ok_handler(request):
    body = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "你好"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    return httpx.Response(200, json=body, request=request)


def _toolcall_handler(request):
    body = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "weather", "arguments": '{"city": "上海"}'},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    return httpx.Response(200, json=body, request=request)


class TestGateway(unittest.IsolatedAsyncioTestCase):
    async def test_success(self):
        gw = _make_gateway(_ok_handler)
        result = await gw.chat(_MSGS, "m1")
        self.assertEqual(result.content, "你好")
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.usage["total_tokens"], 15)

    async def test_tool_calls_parsed(self):
        gw = _make_gateway(_toolcall_handler)
        result = await gw.chat(_MSGS, "m1")
        self.assertIsNone(result.content)
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0]["function"]["name"], "weather")

    async def test_429_retry_then_success(self):
        state = {"calls": 0}

        def handler(request):
            state["calls"] += 1
            if state["calls"] == 1:
                return httpx.Response(
                    429, json={"error": {"message": "rate"}}, headers={"Retry-After": "0"}, request=request
                )
            return _ok_handler(request)

        gw = _make_gateway(handler)
        with patch("infra.llm_gateway.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            result = await gw.chat(_MSGS, "m1")
        self.assertEqual(state["calls"], 2)
        self.assertTrue(sleep_mock.called)
        self.assertEqual(result.content, "你好")

    async def test_429_exhausted_raises(self):
        state = {"calls": 0}

        def handler(request):
            state["calls"] += 1
            return httpx.Response(429, json={"error": {"message": "rate"}}, request=request)

        gw = _make_gateway(handler, max_retries=2)
        with patch("infra.llm_gateway.asyncio.sleep", new=AsyncMock()):
            with self.assertRaises(LLMRateLimitedError):
                await gw.chat(_MSGS, "m1")
        self.assertEqual(state["calls"], 3)

    async def test_401_no_retry(self):
        state = {"calls": 0}

        def handler(request):
            state["calls"] += 1
            return httpx.Response(401, json={"error": {"message": "bad key"}}, request=request)

        gw = _make_gateway(handler, max_retries=2)
        with patch("infra.llm_gateway.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            with self.assertRaises(LLMAuthError):
                await gw.chat(_MSGS, "m1")
        self.assertEqual(state["calls"], 1)
        self.assertFalse(sleep_mock.called)

    async def test_503_retry_then_success(self):
        state = {"calls": 0}

        def handler(request):
            state["calls"] += 1
            if state["calls"] == 1:
                return httpx.Response(503, text="service unavailable", request=request)
            return _ok_handler(request)

        gw = _make_gateway(handler)
        with patch("infra.llm_gateway.asyncio.sleep", new=AsyncMock()):
            result = await gw.chat(_MSGS, "m1")
        self.assertEqual(state["calls"], 2)
        self.assertEqual(result.content, "你好")

    async def test_timeout_classified(self):
        def handler(request):
            raise httpx.ReadTimeout("timed out", request=request)

        gw = _make_gateway(handler, max_retries=1)
        with patch("infra.llm_gateway.asyncio.sleep", new=AsyncMock()):
            with self.assertRaises(LLMTimeoutError):
                await gw.chat(_MSGS, "m1")

    async def test_network_error_includes_cause_detail(self):
        """诊断日志回归：ConnectError 的底层原因（DNS/超时/拒绝）必须出现在错误消息里"""

        def handler(request):
            try:
                raise OSError("[Errno -2] Name or service not known")
            except OSError as e:
                raise httpx.ConnectError("All connection attempts failed", request=request) from e

        gw = _make_gateway(handler, max_retries=0)
        with self.assertRaises(LLMNetworkError) as ctx:
            await gw.chat(_MSGS, "m1")
        self.assertIn("All connection attempts failed", str(ctx.exception))
        self.assertIn("[Errno -2] Name or service not known", str(ctx.exception))

    async def test_error_body_base64_sanitized(self):
        blob = "data:image/png;base64," + "D" * 200

        def handler(request):
            return httpx.Response(200, json={"error": {"message": f"boom {blob}"}}, request=request)

        gw = _make_gateway(handler, max_retries=0)
        with self.assertRaises(LLMUpstreamError) as ctx:
            await gw.chat(_MSGS, "m1")
        self.assertNotIn("DDDD", str(ctx.exception))
        self.assertIn("boom", str(ctx.exception))

    async def test_invalid_json_raises_parse_error(self):
        def handler(request):
            return httpx.Response(200, text="not json", request=request)

        gw = _make_gateway(handler, max_retries=0)
        with self.assertRaises(LLMParseError):
            await gw.chat(_MSGS, "m1")

    async def test_missing_choices_raises_parse_error(self):
        def handler(request):
            return httpx.Response(200, json={"foo": "bar"}, request=request)

        gw = _make_gateway(handler, max_retries=0)
        with self.assertRaises(LLMParseError):
            await gw.chat(_MSGS, "m1")

    async def test_empty_content_stripped_to_none(self):
        def handler(request):
            body = {"choices": [{"message": {"role": "assistant", "content": "   "}, "finish_reason": "stop"}]}
            return httpx.Response(200, json=body, request=request)

        gw = _make_gateway(handler)
        result = await gw.chat(_MSGS, "m1")
        self.assertIsNone(result.content)


if __name__ == "__main__":
    unittest.main()
