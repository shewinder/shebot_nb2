"""aichat 运行时消息插入测试。

用法：.venv/bin/python test/aichat/test_runtime_insertion.py
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parents[2].resolve()
load_dotenv(str(PROJECT_ROOT / ".env.prod"))

import nonebot  # noqa: E402
nonebot.init()

sys.path.insert(0, str(PROJECT_ROOT))

from hoshino.modules.aichat.aichat import chat  # noqa: E402
from hoshino.modules.aichat.aichat.chat_executor import (  # noqa: E402
    APIResponse,
    ChatExecutor,
    ChatResult,
)
from hoshino.modules.aichat.aichat.infra import AppError  # noqa: E402
from hoshino.modules.aichat.aichat.session import (  # noqa: E402
    PendingInput,
    Session,
    session_manager,
)


class TestSessionRuntimeInbox(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session("runtime_inbox", 1)
        self.bot = SimpleNamespace()
        self.event = SimpleNamespace()

    def tearDown(self) -> None:
        self.session.dispose()

    def test_claim_or_enqueue_is_atomic_and_fifo(self) -> None:
        owner, sequence, turn_id, preceding = self.session.claim_turn_or_enqueue(
            "first", [], [], self.bot, self.event, "#first",
        )
        self.assertTrue(owner)
        self.assertIsNone(sequence)
        self.assertIsNotNone(turn_id)
        self.assertEqual(preceding, [])

        second = self.session.claim_turn_or_enqueue(
            "second", ["image"], [], self.bot, self.event, "#second",
        )
        third = self.session.claim_turn_or_enqueue(
            "third", [], ["video"], self.bot, self.event, "#third",
        )
        self.assertEqual(second[:2], (False, 1))
        self.assertEqual(third[:2], (False, 2))

        pending = self.session.finish_turn_or_drain_pending_inputs()
        self.assertEqual([item.user_input for item in pending or []], ["second", "third"])
        self.assertTrue(self.session.turn_active)
        self.assertIsNone(self.session.finish_turn_or_drain_pending_inputs())
        self.assertFalse(self.session.turn_active)

    def test_queue_limit_and_busy_session_not_expired(self) -> None:
        old_limit = self.session.MAX_PENDING_INPUTS
        self.session.MAX_PENDING_INPUTS = 1
        try:
            self.session.last_active = 0
            self.assertTrue(self.session.claim_turn_or_enqueue(
                "first", [], [], self.bot, self.event,
            )[0])
            self.assertEqual(self.session.claim_turn_or_enqueue(
                "second", [], [], self.bot, self.event,
            )[1], 1)
            self.assertEqual(self.session.claim_turn_or_enqueue(
                "third", [], [], self.bot, self.event,
            )[:2], (False, None))
            self.assertFalse(self.session.is_expired())
        finally:
            self.session.MAX_PENDING_INPUTS = old_limit

    def test_dispose_clears_runtime_state(self) -> None:
        self.session.claim_turn_or_enqueue("first", [], [], self.bot, self.event)
        self.session.claim_turn_or_enqueue("second", [], [], self.bot, self.event)
        self.session.dispose()
        self.assertFalse(self.session.turn_active)
        self.assertEqual(self.session.pending_input_count(), 0)


class TestExecutorInsertionBoundary(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.session = Session("runtime_executor", 1)
        self.executor = ChatExecutor(self.session)

    async def asyncTearDown(self) -> None:
        self.session.dispose()

    async def test_inserted_message_is_seen_after_complete_tool_batch(self) -> None:
        requests: List[List[Dict[str, Any]]] = []
        tool_calls = [
            {"id": "call_1", "function": {"name": "tool_1", "arguments": "{}"}},
            {"id": "call_2", "function": {"name": "tool_2", "arguments": "{}"}},
        ]

        async def call_api(messages, api_config, tools=None):
            requests.append([dict(message) for message in messages])
            if len(requests) == 1:
                return APIResponse(
                    tool_calls=tool_calls,
                    assistant_message={"role": "assistant", "tool_calls": tool_calls},
                )
            return APIResponse(content="done")

        async def execute_tool(tool_call, context=None):
            return {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": f"result-{tool_call['id']}",
            }

        callback = AsyncMock(return_value=[{"role": "user", "content": "inserted"}])
        with patch.object(self.executor, "_call_ai_api", side_effect=call_api), \
                patch.object(self.executor, "_execute_tool_call", side_effect=execute_tool):
            result = await self.executor._chat_with_api(
                messages=[{"role": "user", "content": "first"}],
                api_config={"supports_tools": True},
                tools=[{"type": "function"}],
                max_tool_rounds=3,
                before_next_request=callback,
            )

        self.assertEqual(result.content, "done")
        self.assertEqual(callback.await_count, 1)
        roles = [message["role"] for message in requests[1]]
        self.assertEqual(roles, ["user", "assistant", "tool", "tool", "user"])
        self.assertEqual(requests[1][-1]["content"], "inserted")

    async def test_final_response_does_not_consume_pending_callback(self) -> None:
        callback = AsyncMock(return_value=[{"role": "user", "content": "inserted"}])
        with patch.object(
            self.executor,
            "_call_ai_api",
            AsyncMock(return_value=APIResponse(content="done")),
        ):
            result = await self.executor._chat_with_api(
                messages=[{"role": "user", "content": "first"}],
                api_config={"supports_tools": True},
                tools=[{"type": "function"}],
                max_tool_rounds=3,
                before_next_request=callback,
            )
        self.assertEqual(result.content, "done")
        callback.assert_not_awaited()


class TestTurnContinuation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.session = Session("runtime_turn", 1)
        self.bot = SimpleNamespace(send=AsyncMock())
        self.event = SimpleNamespace()
        owner, _, self.turn_id, _ = self.session.claim_turn_or_enqueue(
            "first", [], [], self.bot, self.event,
        )
        self.assertTrue(owner)

    async def asyncTearDown(self) -> None:
        self.session.dispose()

    async def test_messages_arriving_during_final_response_continue_fifo(self) -> None:
        seen: List[str] = []

        async def run_chat(bot, event, session, user_input, image_urls, video_urls, api_config):
            seen.append(user_input)
            if user_input == "first":
                session.enqueue_pending_input("second", [], [], bot, event)
                session.enqueue_pending_input("third", [], [], bot, event)

        first = PendingInput("first", [], [], self.bot, self.event)
        with patch.object(chat, "_run_chat", side_effect=run_chat):
            await chat._run_turn(self.session, first, {})

        self.assertEqual(seen, ["first", "second", "third"])
        self.assertFalse(self.session.turn_active)

    async def test_chat_checkpoint_commits_inserted_message_to_history(self) -> None:
        captured: List[Dict[str, Any]] = []
        self.session.enqueue_pending_input("inserted", [], [], self.bot, self.event)
        event = SimpleNamespace(user_id=1, group_id=None)

        async def execute_chat(executor, **kwargs):
            captured.extend(await kwargs["before_next_request"]())
            return ChatResult(content="done")

        with patch.object(ChatExecutor, "chat", autospec=True, side_effect=execute_chat), \
                patch.object(chat, "send_response", AsyncMock(return_value=True)):
            await chat._run_chat(
                self.bot,
                event,
                self.session,
                "first",
                [],
                [],
                {"supports_multimodal": False},
            )

        self.assertEqual([message["content"] for message in captured], ["inserted"])
        self.assertEqual(
            [message.get("content") for message in self.session.messages],
            ["first", "inserted", "done"],
        )

    async def test_batched_numeric_inputs_share_latest_choices(self) -> None:
        self.session.enqueue_pending_input("1", [], [], self.bot, self.event, "1")
        self.session.enqueue_pending_input("2", [], [], self.bot, self.event, "2")
        captured: List[Dict[str, Any]] = []
        event = SimpleNamespace(user_id=1, group_id=None)

        async def execute_chat(executor, **kwargs):
            self.session.add_message(
                "assistant",
                "[CHOICES]\n1. first option\n2. second option\n[/CHOICES]",
            )
            captured.extend(await kwargs["before_next_request"]())
            return ChatResult(content="done")

        with patch.object(ChatExecutor, "chat", autospec=True, side_effect=execute_chat), \
                patch.object(chat, "send_response", AsyncMock(return_value=True)):
            await chat._run_chat(
                self.bot,
                event,
                self.session,
                "first",
                [],
                [],
                {"supports_multimodal": False},
            )

        self.assertEqual(
            [message["content"] for message in captured],
            ["first option", "second option"],
        )

    async def test_api_error_rolls_back_batch_and_preserves_inserted_message(self) -> None:
        self.session.enqueue_pending_input("inserted", [], [], self.bot, self.event)
        event = SimpleNamespace(user_id=1, group_id=None)

        async def execute_chat(executor, **kwargs):
            await kwargs["before_next_request"]()
            return ChatResult(error=AppError("temporary", code="llm.unavailable"))

        with patch.object(ChatExecutor, "chat", autospec=True, side_effect=execute_chat):
            result = await chat._run_chat(
                self.bot,
                event,
                self.session,
                "first",
                [],
                [],
                {"supports_multimodal": False},
            )

        self.assertFalse(result)
        self.assertEqual(self.session.messages, [])
        self.assertEqual(self.session.pending_input_count(), 1)
        self.assertEqual(self.session.drain_pending_inputs()[0].user_input, "inserted")
        self.bot.send.assert_awaited_once()

    async def test_failed_pending_item_is_requeued(self) -> None:
        pending = PendingInput("inserted", [], [], self.bot, self.event)
        self.session.enqueue_pending_input(
            pending.user_input, pending.image_urls, pending.video_urls,
            pending.bot, pending.event,
        )
        first = PendingInput("first", [], [], self.bot, self.event)
        with patch.object(chat, "_run_chat", AsyncMock(side_effect=[True, False])):
            await chat._run_turn(self.session, first, {})

        self.assertEqual(self.session.pending_input_count(), 1)
        self.assertEqual(self.session.drain_pending_inputs()[0].user_input, "inserted")

    async def test_exception_releases_expected_turn(self) -> None:
        first = PendingInput("first", [], [], self.bot, self.event)
        with patch.object(chat, "_run_chat", AsyncMock(side_effect=RuntimeError("boom"))):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                try:
                    await chat._run_turn(self.session, first, {})
                finally:
                    self.session.end_turn(self.turn_id)
        self.assertFalse(self.session.turn_active)


class TestRuntimeIngress(unittest.IsolatedAsyncioTestCase):
    async def test_get_or_create_keeps_existing_session(self) -> None:
        user_id = 913578
        try:
            first = session_manager.get_or_create_session(user_id, persona="one")
            second = session_manager.get_or_create_session(user_id, persona="two")
            self.assertIs(first, second)
            self.assertEqual(second.persona, "one")
        finally:
            session_manager.clear_session(user_id)

    async def test_busy_session_enqueues_without_starting_second_runner(self) -> None:
        user_id = 913579
        session = session_manager.create_session(user_id)
        bot = SimpleNamespace(send=AsyncMock())
        event = SimpleNamespace(
            user_id=user_id,
            message="#inserted",
            reply=None,
            get_message=lambda: [],
        )
        owner, _, _, _ = session.claim_turn_or_enqueue(
            "first", [], [], bot, event,
        )
        self.assertTrue(owner)

        api_config = {"api_key": "test", "supports_multimodal": False}
        try:
            with patch.object(chat.api_manager, "get_api_config", return_value=api_config), \
                    patch.object(chat, "_run_turn", AsyncMock()) as run_turn:
                await chat.handle_ai_chat(bot, event)
            run_turn.assert_not_awaited()
            self.assertEqual(session.pending_input_count(), 1)
            self.assertEqual(session.drain_pending_inputs()[0].user_input, "inserted")
            bot.send.assert_awaited_once()
        finally:
            session_manager.clear_session(user_id)


if __name__ == "__main__":
    unittest.main()
