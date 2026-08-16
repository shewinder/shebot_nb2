"""用户图片偏好画像工具

替代已删除的通用 read_file/write_file 的画像专用读写：
- user_id 从 session 自动获取，AI 永远只能读写当前用户自己的画像
- 画像文件路径与 pixivrank（ai_filter.py/data_source.py）的读取路径一致：
  data/aichat/preferences/{user_id}.md
"""
from pathlib import Path
from typing import Annotated, Any, Dict, Optional, TYPE_CHECKING

from loguru import logger
from pydantic import Field

from hoshino import userdata_dir

from ..registry import tool_registry, ok, fail

if TYPE_CHECKING:
    from ...session import Session

# 画像长度上限（与 image_preference SKILL 的"控制长度"约定一致）
MAX_PREFERENCE_LENGTH = 5000


def _preference_path(user_id: int) -> Path:
    return userdata_dir.joinpath("aichat", "preferences", f"{user_id}.md")


@tool_registry.register(
    description="""读取当前用户的图片偏好画像（Markdown 文件）。

画像记录用户对图片/插画风格的偏好模式，由图片分析流程维护。
文件不存在时返回空内容。""",
)
async def read_preference(
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    if not session or not session.user_id:
        return fail("无法获取用户信息", error="Missing user context")

    path = _preference_path(session.user_id)
    if not path.exists():
        return ok("", metadata={"exists": False})

    try:
        content = path.read_text(encoding="utf-8")
        return ok(content, metadata={"exists": True, "length": len(content)})
    except Exception as e:
        logger.exception(f"读取画像失败 user_id={session.user_id}: {e}")
        return fail(f"读取画像失败: {e}", error=str(e))


@tool_registry.register(
    description="""覆盖写入当前用户的图片偏好画像。

⚠️ 重要规则：
1. 必须先调用 read_preference 读取现有画像
2. 写入时必须保留未改动的部分，只更新本次分析涉及的内容
3. 总长度不要超过 5000 字符，接近上限时先精简旧内容
4. 保持 Markdown 结构（## 标题分节）

注意：只能写入当前用户自己的画像，user_id 由系统自动确定。""",
)
async def write_preference(
    content: Annotated[str, Field(description="完整的画像 Markdown 内容（必须包含所有历史内容，不能遗漏）")],
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    if not session or not session.user_id:
        return fail("无法获取用户信息", error="Missing user context")

    content = content.strip() if content else ""
    if not content:
        return fail("画像内容不能为空", error="Empty content")

    if len(content) > MAX_PREFERENCE_LENGTH:
        return fail(
            f"画像内容过长（{len(content)} 字符），请精简到 {MAX_PREFERENCE_LENGTH} 字符以内。",
            error="Content too long",
            metadata={"max_length": MAX_PREFERENCE_LENGTH, "current_length": len(content)},
        )

    try:
        path = _preference_path(session.user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ok("画像已更新", metadata={"length": len(content)})
    except Exception as e:
        logger.exception(f"写入画像失败 user_id={session.user_id}: {e}")
        return fail(f"写入画像失败: {e}", error=str(e))
