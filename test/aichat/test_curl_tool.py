"""curl 工具安全测试（URL/SSRF 校验、头注入防护、参数构造）

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_curl_tool.py
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

import nonebot  # noqa: E402
nonebot.init()

sys.path.insert(0, str(_PROJECT_ROOT))

from hoshino.modules.aichat.aichat.tools.builtin import curl_tool  # noqa: E402
from hoshino.modules.aichat.aichat.tools.builtin.curl_tool import (  # noqa: E402
    CurlInput,
    _build_args,
    _validate_headers,
    _validate_url,
)


class TestUrlValidation(unittest.TestCase):
    def test_scheme_rejected(self):
        ok, _ = _validate_url("ftp://example.com/x")
        self.assertFalse(ok)
        ok, _ = _validate_url("file:///etc/passwd")
        self.assertFalse(ok)

    def test_private_ip_literals_rejected(self):
        for url in [
            "http://127.0.0.1:8080/x",
            "http://192.168.1.5/x",
            "http://10.0.0.1/x",
            "http://172.16.0.2/x",
            "http://169.254.169.254/latest/meta-data",
        ]:
            ok, msg = _validate_url(url)
            self.assertFalse(ok, f"应拒绝内网地址: {url}")

    def test_public_ip_allowed(self):
        ok, _ = _validate_url("https://1.1.1.1/x")
        self.assertTrue(ok)

    def test_domain_resolving_private_rejected(self):
        with patch.object(
            curl_tool.socket, "getaddrinfo",
            return_value=[(None, None, None, None, ("192.168.0.10", 0))],
        ):
            ok, msg = _validate_url("https://evil.example.com/x")
        self.assertFalse(ok)
        self.assertIn("内网", msg)

    def test_domain_public_allowed(self):
        with patch.object(
            curl_tool.socket, "getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            ok, _ = _validate_url("https://example.com/x")
        self.assertTrue(ok)


class TestHeaderValidation(unittest.TestCase):
    def test_crlf_injection_rejected(self):
        ok, _ = _validate_headers(["X-Test: a\r\nInjected: b"])
        self.assertFalse(ok)

    def test_missing_colon_rejected(self):
        ok, _ = _validate_headers(["nocolon"])
        self.assertFalse(ok)

    def test_valid_headers(self):
        ok, _ = _validate_headers(["Authorization: Bearer x", "Content-Type: application/json"])
        self.assertTrue(ok)


class TestBuildArgs(unittest.TestCase):
    def test_get_request(self):
        params = CurlInput(url="https://example.com/x")
        args = _build_args(params)
        self.assertIn("GET", args)
        self.assertEqual(args[-1], "https://example.com/x")

    def test_post_with_data_and_headers(self):
        params = CurlInput(
            url="https://example.com/api",
            method="POST",
            data='{"a": 1}',
            headers=["Content-Type: application/json"],
        )
        args = _build_args(params)
        self.assertIn("POST", args)
        self.assertIn('{"a": 1}', args)
        self.assertIn("Content-Type: application/json", args)


if __name__ == "__main__":
    unittest.main()
