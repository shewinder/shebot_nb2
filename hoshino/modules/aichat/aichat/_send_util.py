"""消息发送工具

为 send_response、scheduler、background_task 提供统一的 AI 消息发送逻辑。
"""
from typing import Any, List, Optional

from loguru import logger

from hoshino import MessageSegment


async def send_messages(
    bot,
    messages: List[Any],
    group_id: Optional[int] = None,
    user_id: int | None = None,
) -> bool:
    """发送消息列表，多消息时群聊优先合并为转发消息"""
    if not messages:
        return False

    if group_id and len(messages) > 1:
        try:
            from hoshino.util.message_util import send_group_forward_msg

            msg_segments: List[MessageSegment] = []
            for msg in messages:
                msg_segments.extend(msg)
            await send_group_forward_msg(bot, group_id, msg_segments)
            return True
        except Exception as e:
            logger.warning(f"转发消息发送失败，降级为逐条发送: {e}")

    success_count = 0
    for i, msg in enumerate(messages):
        try:
            if group_id:
                await bot.send_group_msg(group_id=group_id, message=msg)
            else:
                await bot.send_private_msg(user_id=user_id, message=msg)
            success_count += 1
        except Exception as e:
            logger.error(f"发送第 {i + 1}/{len(messages)} 条消息失败: {e}")

    return success_count > 0


async def send_ai_response(
    content: str,
    session,
    *,
    group_id: Optional[int] = None,
    user_id: int = 0,
    enable_markdown: bool = False,
    markdown_min_length: int = 100,
    at_user_id: int | None = None,
) -> bool:
    """统一 AI 回复发送入口：图片标识符替换 + Markdown 渲染 + 发送

    Args:
        content: AI 回复原始文本（可能包含图片标识符）
        session: Session 实例（None 时跳过标识符替换和 Markdown 渲染）
        group_id: 群组ID（None 为私聊）
        user_id: 用户ID
        enable_markdown: 是否启用 Markdown 渲染
        markdown_min_length: Markdown 渲染最小文本长度
        at_user_id: 需要 @ 的用户 ID（会在第一条消息前添加 @）
    """
    if not content or not content.strip():
        return False

    from hoshino import get_bot_list

    bots = get_bot_list()
    if not bots:
        logger.warning("没有可用的 Bot，无法发送消息")
        return False

    bot = bots[0]

    if session:
        messages = await session.build_message(
            content,
            enable_markdown=enable_markdown,
            markdown_min_length=markdown_min_length,
        )
    else:
        messages = [MessageSegment.text(content)]

    messages = [m for m in messages if m]
    if not messages:
        return False

    # @ 提醒
    if at_user_id and group_id and messages:
        try:
            at_prefix = MessageSegment.at(at_user_id) + MessageSegment.text(" ")
            messages[0] = at_prefix + messages[0]
        except Exception as e:
            logger.warning(f"构造 @ 消息失败: {e}")

    return await send_messages(bot, messages, group_id=group_id, user_id=user_id)
