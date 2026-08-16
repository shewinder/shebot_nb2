"""Reply 管道 — 结构化回复的构建与发送

把 AI 回复文本解析为有序的 ReplyPart 序列（text / image / at），
替代 _send_util 里"裸正则拆分 + 静默丢弃"的做法。

改进点（相对旧实现）：
- 容错：容忍标识符两侧空白（< ai_image_1 >）；
- 保序：图片/@ 保留在原文中的相对位置；
- 降级：解析失败的标识符转字面文本 + warning（不再静默消失）；
- 会话级去重：同轮已发送的图片不重复发（on_content 中间轮与最终回复之间）；
- 兜底：本轮新创建但未被模型引用的 ai 图片自动补发。
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Set, TYPE_CHECKING

from loguru import logger

from hoshino import Message, MessageSegment
from hoshino.sres import Res
from hoshino.util import get_bot_list
from hoshino.util.message_util import send_group_forward_msg

from .md_render import render_text_if_markdown

if TYPE_CHECKING:
    from .session import Session

# 图片/at 标识符（容错空白）。IMAGE_TOKEN_RE 同时被 agent_loop.rehome_images 复用
IMAGE_TOKEN_RE = re.compile(r"<\s*(user_image_\d+|ai_image_\d+)\s*>")
# @ 仅匹配合法 QQ 号长度（5-11 位），避免模型解释语法时输出短数字被误触发
AT_TOKEN_RE = re.compile(r"<\s*@(\d{5,11})\s*>")
TOKEN_RE = re.compile(r"<\s*(user_image_\d+|ai_image_\d+)\s*>|<\s*@(\d{5,11})\s*>")


@dataclass
class ReplyPart:
    kind: str            # "text" | "image" | "at"
    text: str = ""
    identifier: str = ""
    qq_id: int = 0


async def build_reply(
    content: str,
    session: Optional["Session"] = None,
    *,
    auto_attach: bool = True,
) -> List[ReplyPart]:
    """将回复文本解析为有序 ReplyPart 列表

    session 为 None 时（后台发送的兜底场景）图片标识符降级为字面文本。
    """
    parts: List[ReplyPart] = []
    pos = 0
    referenced: Set[str] = set()

    for m in TOKEN_RE.finditer(content):
        if m.start() > pos:
            text = content[pos:m.start()]
            if text.strip():
                parts.append(ReplyPart(kind="text", text=text))

        if m.group(1):  # 图片标识符
            norm = f"<{m.group(1)}>"
            if session is None:
                parts.append(ReplyPart(kind="text", text=norm))
            elif norm in referenced:
                continue
            elif session._image_store.get(norm) is None:
                logger.warning(f"回复引用了不存在的图片标识符，降级为字面文本: {norm}")
                parts.append(ReplyPart(kind="text", text=norm))
            elif norm in session._turn_sent_images:
                continue
            else:
                parts.append(ReplyPart(kind="image", identifier=norm))
                session._turn_sent_images.add(norm)
                referenced.add(norm)
        else:  # @标识符
            parts.append(ReplyPart(kind="at", qq_id=int(m.group(2))))

        pos = m.end()

    if pos < len(content):
        text = content[pos:]
        if text.strip():
            parts.append(ReplyPart(kind="text", text=text))

    if auto_attach and session is not None:
        threshold = getattr(session, "last_user_msg_at", 0.0)
        for img in session._image_store.list_all():
            if img.source != "ai" or img.created_at < threshold:
                continue
            if img.identifier in referenced or img.identifier in session._turn_sent_images:
                continue
            parts.append(ReplyPart(kind="image", identifier=img.identifier))
            session._turn_sent_images.add(img.identifier)
            referenced.add(img.identifier)

    return parts


def _resolve_image_segment(session: Optional["Session"], identifier: str) -> Optional[MessageSegment]:
    """解析图片标识符为 MessageSegment（文件缺失时返回 None）"""
    if session is None:
        return None
    entry = session._image_store.get(identifier)
    if not entry or not entry.file_path.exists():
        return None
    try:
        return Res.image(entry.file_path)
    except Exception:
        return None


def _build_plain_messages(
    parts: List[ReplyPart], image_segments: List[MessageSegment]
) -> List[Message]:
    """plain 模式：文本+@内联，图片追加或分批"""
    msg = Message()
    messages: List[Message] = []

    for p in parts:
        if p.kind == "image":
            continue
        if p.kind == "at":
            msg += MessageSegment.at(p.qq_id)
        elif p.text.strip():
            msg += MessageSegment.text(p.text)

    if len(image_segments) > 3:
        if msg:
            messages.append(msg)
        for seg in image_segments:
            messages.append(Message(seg))
        return messages

    for seg in image_segments:
        msg += seg
    if msg:
        messages.append(msg)
    return messages


async def _build_markdown_messages(
    parts: List[ReplyPart],
    image_segments: List[MessageSegment],
    markdown_min_length: int,
) -> List[Message]:
    """Markdown 模式：文本走渲染，图片独立，@ 独立消息"""
    clean_text = "".join(p.text for p in parts if p.kind == "text").strip()
    at_segments = [MessageSegment.at(p.qq_id) for p in parts if p.kind == "at"]

    messages: List[Message] = []

    if clean_text:
        text_msg: Optional[MessageSegment] = None
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

    if at_segments:
        at_msg = Message()
        for seg in at_segments:
            at_msg += seg
        messages.append(at_msg)

    for seg in image_segments:
        messages.append(Message(seg))

    return messages


async def _send_messages(
    bot,
    messages: List[Message],
    group_id: Optional[int] = None,
    user_id: Optional[int] = None,
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


async def send_reply(
    parts: List[ReplyPart],
    session: Optional["Session"] = None,
    *,
    group_id: Optional[int] = None,
    user_id: Optional[int] = None,
    enable_markdown: bool = False,
    markdown_min_length: int = 100,
    at_user_id: Optional[int] = None,
) -> bool:
    """发送结构化回复"""
    if not parts:
        return False

    bots = get_bot_list()
    if not bots:
        logger.warning("没有可用的 Bot，无法发送消息")
        return False
    bot = bots[0]

    image_segments: List[MessageSegment] = []
    for p in parts:
        if p.kind == "image":
            seg = _resolve_image_segment(session, p.identifier)
            if seg:
                image_segments.append(seg)

    if enable_markdown:
        messages = await _build_markdown_messages(parts, image_segments, markdown_min_length)
    else:
        messages = _build_plain_messages(parts, image_segments)

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

    return await _send_messages(bot, messages, group_id=group_id, user_id=user_id)
