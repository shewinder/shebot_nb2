"""消息发送兼容层

send_ai_response 是 Reply 管道（reply.py）的薄包装，保留历史签名，
供 chat.py / scheduler_core / background_task_core 继续调用。
新增发送逻辑请直接使用 reply.build_reply / reply.send_reply。
"""
from typing import Optional, TYPE_CHECKING

from .reply import build_reply, send_reply

if TYPE_CHECKING:
    from .session import Session


async def send_ai_response(
    content: str,
    session: Optional["Session"],
    *,
    group_id: Optional[int] = None,
    user_id: int = 0,
    enable_markdown: bool = False,
    markdown_min_length: int = 100,
    at_user_id: Optional[int] = None,
) -> bool:
    """统一 AI 回复发送入口（兼容旧签名，内部走 Reply 管道）"""
    if not content or not content.strip():
        return False

    parts = await build_reply(content, session)
    return await send_reply(
        parts,
        session,
        group_id=group_id,
        user_id=user_id,
        enable_markdown=enable_markdown,
        markdown_min_length=markdown_min_length,
        at_user_id=at_user_id,
    )
