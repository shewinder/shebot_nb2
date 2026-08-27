"""
只读文件工具（read_file）

AI 可读取 data 目录下的文本文件（如自己生成的数据、日志、配置产物）。
路径校验复用 store_images 的 _check_path：禁止绝对路径与路径遍历，
resolve 后必须仍在 data 目录内。仅只读，不提供写入面。
"""
from typing import Annotated, Any, Dict, Optional, TYPE_CHECKING

from pydantic import Field

from ..registry import tool_registry, ok, fail
from .store_images import ALLOWED_ROOT, _check_path

if TYPE_CHECKING:
    from ...session import Session

# 单文件读取上限：防止把超大/二进制文件塞进模型上下文
MAX_READ_SIZE = 100 * 1024


@tool_registry.register(description="读取 data 目录下的文本文件内容（相对路径，如 aichat/xxx/meta.json）")
async def read_file(
    path: Annotated[str, Field(description="文件路径（相对于 data 目录，禁止绝对路径和 ..）")],
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    """读取 data 目录内文本文件"""
    is_valid, full_path = _check_path(path)
    if not is_valid:
        return fail("非法路径：只允许 data 目录内的相对路径")

    if not full_path.exists():
        return ok("", metadata={"exists": False})

    if full_path.stat().st_size > MAX_READ_SIZE:
        return fail(f"文件过大（>{MAX_READ_SIZE // 1024}KB），拒绝读取")

    try:
        content = full_path.read_text(encoding="utf-8")
        return ok(content, metadata={"exists": True})
    except Exception as e:
        return fail(f"读取失败（可能不是文本文件）: {e}")
