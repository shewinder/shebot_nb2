"""agent_loop 单元测试

覆盖：成功路径与注册表清理、并发 session_id 唯一性、API 未配置、
会话标志位、rehome_images 三条路径（映射命中/拷贝/降级）与 auto_attach。

需要 nonebot.init()（agent_loop 依赖 hoshino 链），LLM 用 MockTransport 注入。

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_agent_loop.py
"""
import asyncio
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

import nonebot  # noqa: E402
nonebot.init()

sys.path.insert(0, str(_PROJECT_ROOT))

import httpx  # noqa: E402

import hoshino.modules.aichat.aichat.agent_loop as agent_loop  # noqa: E402
from hoshino.modules.aichat.aichat.agent_loop import (  # noqa: E402
    AgentResult,
    AgentTask,
    rehome_images,
    run_agent_loop,
)
from hoshino.modules.aichat.aichat.chat_executor import ChatResult  # noqa: E402
from hoshino.modules.aichat.aichat.infra import llm_gateway as lg  # noqa: E402
from hoshino.modules.aichat.aichat.session import Session, session_manager  # noqa: E402

_MOCK_BASE = "https://api.mock"
_OK_BODY = {
    "choices": [{"message": {"role": "assistant", "content": "子任务完成"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


def _install_mock_gateway() -> None:
    def handler(request):
        return httpx.Response(200, json=_OK_BODY, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    lg._gateways[_MOCK_BASE] = lg.LLMGateway(_MOCK_BASE, "sk-test", client=client, max_retries=0)


class FakeImageStore:
    """内存假图库：entries 按标识符提供 data_url，list_all 返回列表"""

    def __init__(self, entries=None, list_entries=None):
        self.entries = entries or {}
        self.list_entries = list_entries or []

    def get_data_url(self, identifier):
        entry = self.entries.get(identifier)
        return entry["data_url"] if entry else None

    def get(self, identifier):
        entry = self.entries.get(identifier)
        if not entry:
            return None
        return SimpleNamespace(
            identifier=identifier,
            url=entry.get("url"),
            source=entry.get("source", "ai"),
            file_path=Path("x.png"),
        )

    def list_all(self):
        return self.list_entries

    def clear(self):
        pass


class TestRunAgentLoop(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _install_mock_gateway()
        self.api_cfg = {
            "api_base": _MOCK_BASE,
            "api_key": "sk-test",
            "model": "m1",
            "supports_tools": False,
        }

    async def test_success_and_registry_cleanup(self):
        task = AgentTask(task="测试任务", system_prompt="你是测试子 Agent", user_id=1, api_config=self.api_cfg)
        result = await run_agent_loop(task)
        self.assertEqual(result.result.content, "子任务完成")
        self.assertTrue(result.session.session_id.startswith("agent_"))
        self.assertEqual(len(result.session.session_id.split("_")[-1]), 8)  # uuid hex8 后缀
        self.assertNotIn(result.session.session_id, session_manager.sessions)

    async def test_concurrent_unique_ids(self):
        async def one():
            task = AgentTask(task="并发", system_prompt="x", user_id=1, api_config=self.api_cfg)
            return await run_agent_loop(task)

        r1, r2 = await asyncio.gather(one(), one())
        self.assertNotEqual(r1.session.session_id, r2.session.session_id)
        self.assertNotIn(r1.session.session_id, session_manager.sessions)
        self.assertNotIn(r2.session.session_id, session_manager.sessions)

    async def test_api_unconfigured(self):
        with patch.object(agent_loop.api_manager, "get_api_config", return_value=None):
            task = AgentTask(task="任务", system_prompt="x", user_id=1)
            result = await run_agent_loop(task)
        self.assertEqual(result.result.error, "API 未配置")
        self.assertNotIn(result.session.session_id, session_manager.sessions)

    async def test_session_flags(self):
        task = AgentTask(
            task="任务",
            system_prompt="x",
            user_id=1,
            api_config=self.api_cfg,
            blocked_tools=frozenset({"web_search"}),
            locked_tools=True,
            label="sub:test",
        )
        result = await run_agent_loop(task)
        self.assertEqual(result.session._blocked_tools, frozenset({"web_search"}))
        self.assertTrue(result.session._subagent_locked_tools)
        self.assertEqual(result.session.agent_label, "sub:test")


class TestRehomeImages(unittest.IsolatedAsyncioTestCase):
    def _make_parent(self):
        parent = Session("parent_test_1", 1)
        parent._image_store = FakeImageStore()
        parent.store_ai_image = AsyncMock(return_value="<ai_image_50>")
        parent.store_user_image = AsyncMock(return_value="<user_image_50>")
        return parent

    def _make_child(self, entries=None, list_entries=None):
        child = Session("child_test_1", 1)
        child._image_store = FakeImageStore(entries, list_entries)
        return child

    async def test_mapping_hit_zero_copy(self):
        parent = self._make_parent()
        child = self._make_child({}, [])
        agent_result = AgentResult(
            result=ChatResult(content="看这张 <user_image_1>"),
            session=child,
            image_map={"<user_image_1>": "<user_image_2>"},
        )
        out = await rehome_images(agent_result, parent)
        self.assertEqual(out, "看这张 <user_image_2>")
        parent.store_user_image.assert_not_awaited()
        parent.store_ai_image.assert_not_awaited()

    async def test_copy_path(self):
        parent = self._make_parent()
        child = self._make_child({"<ai_image_1>": {"data_url": "data:image/png;base64,AA", "source": "ai"}}, [])
        agent_result = AgentResult(result=ChatResult(content="图 <ai_image_1>"), session=child)
        out = await rehome_images(agent_result, parent)
        self.assertEqual(out, "图 <ai_image_50>")
        parent.store_ai_image.assert_awaited_once()

    async def test_fallback_placeholder(self):
        parent = self._make_parent()
        child = self._make_child({}, [])
        agent_result = AgentResult(result=ChatResult(content="图 <ai_image_3>"), session=child)
        out = await rehome_images(agent_result, parent)
        self.assertEqual(out, "图 [图片]")
        parent.store_ai_image.assert_not_awaited()

    async def test_auto_attach(self):
        parent = self._make_parent()
        now = time.time()
        img = SimpleNamespace(source="ai", identifier="<ai_image_7>", created_at=now)
        child = self._make_child(
            {"<ai_image_7>": {"data_url": "data:image/png;base64,BB", "source": "ai"}},
            [img],
        )
        child.last_user_msg_at = now - 1
        agent_result = AgentResult(result=ChatResult(content="完成"), session=child)
        out = await rehome_images(agent_result, parent)
        self.assertIn("<ai_image_50>", out)


if __name__ == "__main__":
    unittest.main()
