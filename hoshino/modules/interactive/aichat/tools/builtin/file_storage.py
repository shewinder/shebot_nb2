"""
文件读写工具
"""
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from ..registry import tool_registry, ok, fail

if TYPE_CHECKING:
    from ...session import Session


# 允许访问的根目录（只能是项目下的 data 目录）
ALLOWED_ROOT = Path("data").resolve()


def _check_path(path: str) -> tuple[bool, Path]:
    """检查路径是否合法，返回 (是否合法, 完整路径)"""
    try:
        # 禁止绝对路径和路径遍历
        if path.startswith("/") or ".." in path:
            return False, Path()
        
        full_path = ALLOWED_ROOT / path
        full_path = full_path.resolve()
        
        # 确保在 data 目录下
        if not str(full_path).startswith(str(ALLOWED_ROOT)):
            return False, Path()
        
        return True, full_path
    except Exception:
        return False, Path()


@tool_registry.register(
    name="read_file",
    description="读取文件内容",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径（相对于 data 目录）"
            }
        },
        "required": ["path"]
    }
)
async def read_file(
    path: str,
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    """读取文件"""
    is_valid, full_path = _check_path(path)
    if not is_valid:
        return fail("非法路径")
    
    if not full_path.exists():
        return ok("", metadata={"exists": False})
    
    try:
        content = full_path.read_text(encoding='utf-8')
        return ok(content, metadata={"exists": True})
    except Exception as e:
        return fail(f"读取失败: {e}")


@tool_registry.register(
    name="write_file",
    description="写入文件（完全覆盖）",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径（相对于 data 目录）"
            },
            "content": {
                "type": "string",
                "description": "文件内容"
            }
        },
        "required": ["path", "content"]
    }
)
async def write_file(
    path: str,
    content: str,
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    """写入文件"""
    is_valid, full_path = _check_path(path)
    if not is_valid:
        return fail("非法路径")
    
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding='utf-8')
        return ok("写入成功")
    except Exception as e:
        return fail(f"写入失败: {e}")
