"""群聊消息查询工具

为 AI 提供 query_group_messages 工具，用于查询群聊历史消息。
可用于：群消息总结、上下文回顾、用户发言分析、话题追踪等。
"""
import time
from datetime import datetime
from typing import Any, Dict, Optional, TYPE_CHECKING

from loguru import logger

from ..registry import tool_registry, ok, fail

if TYPE_CHECKING:
    from ...session import Session


@tool_registry.register(
    name="query_group_messages",
    description="""查询本群聊天记录。用于了解群里聊了什么、回顾上下文、分析用户发言等。

典型用法：
- 今天聊了什么：query_group_messages(last_seconds=86400)
- 最近一小时：query_group_messages(last_seconds=3600)
- 最近一周某人的发言：query_group_messages(user_id=123456, last_seconds=604800)
- 关键词搜索：query_group_messages(keyword="某话题", last_seconds=604800)
- 最近上下文：query_group_messages(limit=20) 获取最近20条""",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "integer",
                "description": "用户QQ号，用于筛选特定用户的发言。不传则不限定用户"
            },
            "keyword": {
                "type": "string",
                "description": "关键词搜索，在消息文本中查找。不传则不限定关键词"
            },
            "last_seconds": {
                "type": "integer",
                "description": "往前查多少秒的消息。如：3600=最近一小时，86400=今天，604800=最近一周。不传则不限时间"
            },
            "limit": {
                "type": "integer",
                "description": "返回条数上限，默认100，最大2000"
            }
        },
        "required": []
    }
)
async def query_group_messages(
    user_id: Optional[int] = None,
    keyword: Optional[str] = None,
    last_seconds: Optional[int] = None,
    limit: int = 100,
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    """查询群聊历史消息

    从 groupmsglog 数据库查询当前群的聊天记录。
    支持按用户、关键词、时间范围过滤。

    Args:
        user_id: 筛选特定用户（可选）
        keyword: 关键词搜索（可选）
        last_seconds: 往前查多少秒（可选）
        limit: 返回条数，最大200
        session: 会话对象（自动注入，用于获取当前群号）
    """
    if not session:
        return fail("无法获取会话信息")

    group_id = getattr(session, 'group_id', None)
    if not group_id:
        return fail("当前不在群聊上下文中，无法查询群消息")

    limit = min(max(limit, 1), 2000)

    start_time = int(time.time()) - last_seconds if last_seconds else None

    try:
        from hoshino.modules.groupmsglog._data import search_messages

        messages = search_messages(
            group_id=group_id,
            user_id=user_id,
            keyword=keyword,
            start_time=start_time,
            end_time=None,
            limit=limit,
        )
    except Exception as e:
        logger.exception(f"query_group_messages 数据库查询失败: {e}")
        return fail("查询消息历史失败，请稍后重试", error=str(e))

    if not messages:
        desc_parts = [f"群 {group_id}"]
        if last_seconds:
            desc_parts.append(f"最近 {last_seconds} 秒")
        if user_id:
            desc_parts.append(f"用户 {user_id}")
        if keyword:
            desc_parts.append(f"关键词「{keyword}」")
        return ok(f"（{'，'.join(desc_parts)}内没有找到匹配的消息）")

    lines = [
        f"群 {group_id} 共 {len(messages)} 条消息",
        "---"
    ]
    for m in messages:
        ts = datetime.fromtimestamp(m['time']).strftime('%m-%d %H:%M')
        name = m['card'] or m['nickname'] or str(m['user_id'])
        content = m['content'].replace('\n', ' ')
        if len(content) > 300:
            content = content[:300] + "..."
        lines.append(f"[{ts}] {name}({m['user_id']}): {content}")

    result = "\n".join(lines)
    logger.info(f"query_group_messages: group={group_id}, user={user_id}, keyword={keyword}, "
                f"last_seconds={last_seconds}, limit={limit} → {len(messages)} results")

    return ok(result, metadata={
        "count": len(messages),
        "group_id": group_id,
        "user_id": user_id,
        "keyword": keyword,
        "last_seconds": last_seconds,
    })
