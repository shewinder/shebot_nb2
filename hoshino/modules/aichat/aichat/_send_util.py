"""消息发送工具

为 send_response、scheduler、background_task 提供统一的 AI 消息发送逻辑。
"""
import re
from typing import Any, List, Optional, TYPE_CHECKING

from loguru import logger

from hoshino import Message, MessageSegment
from hoshino.sres import Res
from hoshino.util import get_bot_list
from hoshino.util.message_util import send_group_forward_msg

from .md_render import render_text_if_markdown

if TYPE_CHECKING:
    from .session import Session

# 多媒体标识符正则：<user_image_N> / <ai_image_N> / <@QQ号>
_MEDIA_PATTERN = re.compile(r'<(user_image_\d+|ai_image_\d+|@\d+)>')


async def _resolve_image_segment(session: "Session", identifier: str) -> Optional[MessageSegment]:
    """解析图片标识符为 MessageSegment"""
    entry = session._image_store.get(identifier)
    if not entry or not entry.file_path.exists():
        return None
    try:
        return Res.image(entry.file_path)
    except Exception:
        return None


def _segment_is_image(part: str) -> bool:
    return part.startswith(('user_image_', 'ai_image_'))


def _segment_is_at(part: str) -> bool:
    return part.startswith('@')


async def build_response_messages(
    content: str,
    session: Optional["Session"] = None,
    enable_markdown: bool = False,
    markdown_min_length: int = 100,
) -> List[Message]:
    """将 AI 回复文本构建为 Message 列表，支持多媒体标识符

    标识符：
      <user_image_N> / <ai_image_N> → 图片
      <@QQ号> → @用户
    """
    # 无 session 时跳过媒体标识符解析，但不影响 markdown 渲染
    if not session:
        if enable_markdown and len(content) >= markdown_min_length:
            return await _build_markdown_only(content, markdown_min_length)
        return [Message(MessageSegment.text(content))]

    tokens = _MEDIA_PATTERN.split(content)

    # 收集图片段（去重——AI 可能重复写同一标识符）
    image_segments: List[MessageSegment] = []
    seen: set[str] = set()
    for token in tokens:
        if not token:
            continue
        if _segment_is_image(token) and token not in seen:
            seen.add(token)
            img_seg = await _resolve_image_segment(session, token)
            if img_seg:
                image_segments.append(img_seg)

    if not enable_markdown:
        return await _build_plain_messages(tokens, image_segments)

    return await _build_markdown_messages(tokens, image_segments, markdown_min_length)


async def _build_plain_messages(
    tokens: List[str],
    image_segments: List[MessageSegment],
) -> List[Message]:
    """plain 模式：文本+@内联，图片追加或分批"""
    msg = Message()
    messages: List[Message] = []

    for token in tokens:
        if not token:
            continue
        if _segment_is_image(token):
            continue
        if _segment_is_at(token):
            try:
                qq_id = int(token[1:])
                msg += MessageSegment.at(qq_id)
            except ValueError:
                msg += MessageSegment.text(f"@{token[1:]}")
        else:
            if token.strip():
                msg += MessageSegment.text(token)

    # 追加图片
    if len(image_segments) > 3:
        if msg:
            messages.append(msg)
        for img_seg in image_segments:
            messages.append(Message(img_seg))
        return messages
    else:
        for img_seg in image_segments:
            msg += img_seg
        if msg:
            messages.append(msg)
        return messages if messages else []


async def _build_markdown_only(content: str, markdown_min_length: int) -> List[Message]:
    """纯文本 Markdown 渲染（无 session / 无媒体标识符时用）"""
    if len(content) < markdown_min_length:
        return [Message(MessageSegment.text(content))]
    try:
        img_bytes = await render_text_if_markdown(content, min_length=markdown_min_length)
        if img_bytes:
            return [Message(MessageSegment.image(file=img_bytes))]
    except Exception:
        pass
    return [Message(MessageSegment.text(content))]


async def _build_markdown_messages(
    tokens: List[str],
    image_segments: List[MessageSegment],
    markdown_min_length: int,
) -> List[Message]:
    """Markdown 模式：文本走渲染，图片独立，@ 独立消息"""
    # 拼接非多媒体 token 的文本
    text_parts = [t for t in tokens if t and not _segment_is_image(t) and not _segment_is_at(t)]
    clean_text = "".join(text_parts).strip()

    # @ 段列表
    at_segments = []
    for token in tokens:
        if not token:
            continue
        if _segment_is_at(token):
            try:
                qq_id = int(token[1:])
                at_segments.append(MessageSegment.at(qq_id))
            except ValueError:
                at_segments.append(MessageSegment.text(f"@{token[1:]}"))

    messages = []

    # Markdown 文本渲染（独立于 @，两者互不影响）
    if clean_text:
        text_msg = None
        if len(clean_text) >= markdown_min_length:
            try:
                img_bytes = await render_text_if_markdown(clean_text, min_length=markdown_min_length)
                if img_bytes:
                    text_msg = MessageSegment.image(file=img_bytes)
            except Exception:
                pass

        if text_msg:
            messages.append(Message(text_msg))
        else:
            messages.append(Message(MessageSegment.text(clean_text)))

    # @ 作为独立消息
    if at_segments:
        at_msg = Message()
        for at_seg in at_segments:
            at_msg += at_seg
        messages.append(at_msg)

    # 图片各自独立
    for img_seg in image_segments:
        messages.append(Message(img_seg))

    return messages


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
    """统一 AI 回复发送入口：多媒体标识符替换 + Markdown 渲染 + 发送

    Args:
        content: AI 回复原始文本（可包含 <user_image_N> <ai_image_N> <@QQ>）
        session: Session 实例（None 时跳过标识符替换和 Markdown 渲染）
        group_id: 群组ID（None 为私聊）
        user_id: 用户ID
        enable_markdown: 是否启用 Markdown 渲染
        markdown_min_length: Markdown 渲染最小文本长度
        at_user_id: 额外 @ 的用户 ID（会在第一条消息前添加）
    """
    if not content or not content.strip():
        return False

    bots = get_bot_list()
    if not bots:
        logger.warning("没有可用的 Bot，无法发送消息")
        return False

    bot = bots[0]

    messages = await build_response_messages(
        content,
        session=session,
        enable_markdown=enable_markdown,
        markdown_min_length=markdown_min_length,
    )

    messages = [m for m in messages if m]
    if not messages:
        return False

    # 额外 @ 提醒
    if at_user_id and group_id and messages:
        try:
            at_prefix = MessageSegment.at(at_user_id) + MessageSegment.text(" ")
            messages[0] = at_prefix + messages[0]
        except Exception as e:
            logger.warning(f"构造 @ 消息失败: {e}")

    return await send_messages(bot, messages, group_id=group_id, user_id=user_id)
