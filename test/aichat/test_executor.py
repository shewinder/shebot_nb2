"""chat_executor 单元测试（执行层权限校验 + 工具兜底超时）

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_executor.py
"""
import asyncio
import json
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

from hoshino.modules.aichat.aichat.chat_executor import ChatExecutor  # noqa: E402
from hoshino.modules.aichat.aichat.config import Config  # noqa: E402
from hoshino.modules.aichat.aichat.session import Session  # noqa: E402
from hoshino.modules.aichat.aichat.tools import permission  # noqa: E402
from hoshino.modules.aichat.aichat.tools.registry import ok, tool_registry  # noqa: E402

conf = Config.get_instance('aichat')


def _register_tool(name: str, func):
    tool_registry.register(
        name=name,
        description="测试工具",
        parameters={"type": "object", "properties": {}},
    )(func)


class TestExecutorPermission(unittest.IsolatedAsyncioTestCase):
    async def test_permission_denied_at_execution(self):
        old = conf.tool_permissions
        conf.tool_permissions = {"web_search": "SUPERUSER"}
        try:
            with patch.object(permission, "_get_superusers", return_value={10001}):
                session = Session("exec_perm_1", 99999)
                executor = ChatExecutor(session)
                tool_call = {
                    "id": "call_1",
                    "function": {"name": "web_search", "arguments": json.dumps({"query": "x"})},
                }
                result = await executor._execute_tool_call(tool_call, context={"session": session})
                parsed = json.loads(result["content"])
                self.assertFalse(parsed["success"])
                self.assertIn("超级用户", parsed["error"])
        finally:
            conf.tool_permissions = old

    async def test_superuser_allowed(self):
        old = conf.tool_permissions
        conf.tool_permissions = {"__test_passthrough__": "SUPERUSER"}
        try:
            with patch.object(permission, "_get_superusers", return_value={10001}):

                async def tool():
                    return ok("通过")

                _register_tool("__test_passthrough__", tool)
                session = Session("exec_perm_2", 10001)
                executor = ChatExecutor(session)
                tool_call = {
                    "id": "call_2",
                    "function": {"name": "__test_passthrough__", "arguments": "{}"},
                }
                result = await executor._execute_tool_call(tool_call, context={"session": session})
                parsed = json.loads(result["content"])
                self.assertTrue(parsed["success"])
                self.assertEqual(parsed["content"], "通过")
        finally:
            conf.tool_permissions = old


class TestExecutorTimeout(unittest.IsolatedAsyncioTestCase):
    async def test_tool_timeout(self):
        async def slow_tool():
            await asyncio.sleep(5)
            return ok("done")

        _register_tool("__test_slow__", slow_tool)
        old_timeout = conf.tool_timeout
        conf.tool_timeout = 0.2
        try:
            session = Session("exec_timeout_1", 1)
            executor = ChatExecutor(session)
            tool_call = {
                "id": "call_3",
                "function": {"name": "__test_slow__", "arguments": "{}"},
            }
            result = await executor._execute_tool_call(tool_call, context={"session": session})
            parsed = json.loads(result["content"])
            self.assertFalse(parsed["success"])
            self.assertIn("超时", parsed["error"])
        finally:
            conf.tool_timeout = old_timeout


if __name__ == "__main__":
    unittest.main()
