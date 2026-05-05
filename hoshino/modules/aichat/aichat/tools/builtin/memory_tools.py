"""记忆管理工具

为 AI 提供 read_memory / write_memory 两个工具，使其能够自主读写用户记忆笔记。
"""
from typing import Any, Dict, Optional, TYPE_CHECKING
from loguru import logger

from ..registry import tool_registry, ok, fail
from ...memory import memory_store
from ...config import Config

conf = Config.get_instance('aichat')

if TYPE_CHECKING:
    from ...session import Session


@tool_registry.register(
    name="read_memory",
    description="""读取当前用户的记忆笔记。在修改记忆前，请先调用此工具查看现有内容。

返回该用户的完整 Markdown 格式记忆文件内容。如果这是首次读取，你会看到默认模板。

使用建议：
- 添加新记忆前：先 read，然后在 write 中保留原有内容并追加
- 更新记忆时：先 read，找到需要修改的段落，在 write 中修改该部分，保留其余内容
- 整理记忆时：如果内容过长，可以合并相似条目或删除陈旧信息""",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
async def read_memory(session: Optional["Session"] = None) -> Dict[str, Any]:
    """读取用户记忆笔记

    Args:
        session: 会话对象（自动注入）

    Returns:
        包含记忆内容的 ToolResult
    """
    if not session or not session.user_id:
        return fail("无法获取用户信息", error="Missing user context")

    try:
        content = await memory_store.read(session.user_id)
        return ok(content, metadata={"length": len(content)})
    except Exception as e:
        logger.exception(f"read_memory 失败: {e}")
        return fail("读取记忆失败", error=str(e))


@tool_registry.register(
    name="write_memory",
    description="""覆盖写入当前用户的完整记忆笔记。

⚠️ 重要规则：
1. 必须先调用 read_memory 读取现有内容
2. 写入时必须保留未改动的部分，只修改需要更新的地方
3. 总长度不要超过 5000 字符，如果接近上限请先精简旧内容（合并相似条目、删除陈旧信息）
4. 使用 Markdown 格式，保持 ## 标题结构

正确的使用流程：
1. read_memory() → 获取现有内容
2. 在思考中规划修改
3. write_memory(content="完整的修改后内容") → 写回

错误示例（不要这样做）：
- 没有调用 read_memory 就直接 write_memory（可能导致历史记忆丢失）
- 只写入新内容，遗漏了旧记忆""",
    parameters={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "完整的记忆笔记 Markdown 内容，必须包含所有历史记忆（不能遗漏）"
            }
        },
        "required": ["content"]
    }
)
async def write_memory(content: str, session: Optional["Session"] = None) -> Dict[str, Any]:
    """写入用户记忆笔记

    Args:
        content: 完整的 Markdown 记忆内容
        session: 会话对象（自动注入）

    Returns:
        操作结果的 ToolResult
    """
    if not session or not session.user_id:
        return fail("无法获取用户信息", error="Missing user context")

    content = content.strip() if content else ""
    if not content:
        return fail("记忆内容不能为空", error="Empty content")

    user_id = session.user_id

    try:
        existing = await memory_store.read(user_id)
    except Exception as e:
        logger.exception(f"write_memory 读取现有内容失败: {e}")
        return fail("读取现有记忆失败，无法写入", error=str(e))

    # 安全检查：内容丢失保护
    existing_stripped = existing.strip()
    content_stripped = content.strip()
    if existing_stripped and len(content_stripped) < len(existing_stripped) * 0.4:
        return fail(
            "新内容比现有内容短很多，疑似遗漏了历史记忆。请先调用 read_memory 确认完整内容后再写入。",
            error="Content too short",
            metadata={"existing_length": len(existing_stripped), "new_length": len(content_stripped)}
        )

    # 长度检查
    max_len = conf.memory_max_length
    if len(content) > max_len:
        return fail(
            f"记忆内容过长（{len(content)} 字符），请精简到 {max_len} 字符以内。",
            error="Content too long",
            metadata={"max_length": max_len, "current_length": len(content)}
        )

    success = await memory_store.write(user_id, content)
    if success:
        return ok("记忆已更新", metadata={"length": len(content)})
    else:
        return fail("写入记忆失败", error="Write failed")
