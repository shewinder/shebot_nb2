"""
AI 工具：存储图片到会话
支持从 URL 下载和本地文件路径两种来源，存储后返回标识符供 AI 引用
"""
import base64
import os
from io import BytesIO
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger
from PIL import Image

from hoshino.util import aiohttpx
from hoshino.util.sutil import anti_harmony

from ..registry import tool_registry, ok, fail

if TYPE_CHECKING:
    from ...session import Session


async def _download_image_to_base64(image_url: str, need_anti_harmony: bool = True) -> Optional[str]:
    """下载图片并转换为 base64 data URL

    Args:
        image_url: 图片 URL
        need_anti_harmony: 是否需要反和谐处理（默认启用）
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = await aiohttpx.get(image_url, headers=headers)
        if not resp.ok:
            logger.error(f"下载图片失败: {resp.status_code}, URL: {image_url}")
            return None

        image_data = resp.content
        if not image_data:
            logger.error(f"图片数据为空: {image_url}")
            return None

        # 限制图片大小（10MB）
        if len(image_data) > 10 * 1024 * 1024:
            logger.warning(f"图片过大: {len(image_data)} bytes, URL: {image_url}")
            return None

        # 提取图片格式
        ext = "png"
        content_type = resp.headers.get("Content-Type", "")
        if content_type and content_type.startswith("image/"):
            ext = content_type.split("/")[1].split(";")[0].strip()
            if ext == "jpeg":
                ext = "jpg"
        else:
            if "." in image_url:
                url_ext = os.path.splitext(image_url.split("?")[0])[1].lower()
                if url_ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                    ext = url_ext.lstrip(".")

        # 反和谐处理
        if need_anti_harmony:
            try:
                img = Image.open(BytesIO(image_data))
                # 转换为 RGB 模式（去除透明通道，避免部分格式问题）
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                img = anti_harmony(img)
                # 重新编码
                buffer = BytesIO()
                save_format = 'JPEG' if ext in ['jpg', 'jpeg'] else 'PNG'
                img.save(buffer, format=save_format, quality=95)
                image_data = buffer.getvalue()
                ext = 'jpg' if save_format == 'JPEG' else 'png'
            except Exception as e:
                logger.warning(f"反和谐处理失败，使用原图: {e}")

        base64_data = base64.b64encode(image_data).decode('utf-8')
        image_url_data = f"data:image/{ext};base64,{base64_data}"
        return image_url_data

    except Exception as e:
        logger.exception(f"处理图片失败: {e}, URL: {image_url}")
        return None


def _read_local_image(file_path: str) -> Optional[str]:
    """读取本地图片文件并转换为 base64 data URL

    Args:
        file_path: 相对于 data/ 目录的图片文件路径
    """
    from .file_storage import _check_path

    is_valid, full_path = _check_path(file_path)
    if not is_valid:
        logger.error(f"非法的文件路径: {file_path}")
        return None

    if not full_path.exists():
        logger.error(f"文件不存在: {full_path}")
        return None

    if not full_path.is_file():
        logger.error(f"路径不是文件: {full_path}")
        return None

    # 限制文件大小（10MB）
    file_size = full_path.stat().st_size
    if file_size > 10 * 1024 * 1024:
        logger.warning(f"文件过大: {file_size} bytes, path: {file_path}")
        return None

    # 根据扩展名判断 MIME 类型
    ext_map = {
        ".png": "png",
        ".jpg": "jpg",
        ".jpeg": "jpg",
        ".gif": "gif",
        ".webp": "webp",
    }
    suffix = full_path.suffix.lower()
    ext = ext_map.get(suffix)
    if not ext:
        logger.error(f"不支持的图片格式: {suffix}")
        return None

    try:
        image_data = full_path.read_bytes()
        base64_data = base64.b64encode(image_data).decode('utf-8')
        return f"data:image/{ext};base64,{base64_data}"
    except Exception as e:
        logger.exception(f"读取本地图片失败: {e}, path: {file_path}")
        return None


@tool_registry.register(
    name="store_images",
    description="""存储图片到当前会话，返回标识符供回复引用。

支持两种来源：
1. URL 下载（urls 参数）：从网络下载图片
2. 本地文件（paths 参数）：读取 data/ 目录下的图片文件

两种来源可同时使用，工具会合并处理所有图片。

## 使用方式

1. 准备好图片的 URL 或本地文件路径
2. 调用本工具存储图片
3. 工具返回图片标识符（如 <ai_image_1>, <ai_image_2>）
4. 在你的回复中包含这些标识符，系统会自动发送图片

## 示例

### URL 下载
store_images(urls=["https://example.com/image.jpg"])
# 返回："已准备 1 张图片：<ai_image_1>"

### 本地文件
store_images(paths=["screenshots/baidu.png"])
# 返回："已准备 1 张图片：<ai_image_1>"

### 混合使用
store_images(urls=["https://example.com/1.jpg"], paths=["local/2.png"])
# 返回："已准备 2 张图片：<ai_image_1> <ai_image_2>"

## 注意事项

- urls 和 paths 至少提供一个
- 建议一次最多 5-10 张图片
- 图片过大会自动跳过（限制 10MB）
- 本地路径相对于 data/ 目录，禁止 .. 和绝对路径
- 支持的本地图片格式：png、jpg、gif、webp""",
    parameters={
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "图片 URL 列表，从网络下载图片"
            },
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "本地图片文件路径列表，相对于 data/ 目录"
            }
        },
        "required": []
    },
)
async def store_images(
    urls: Optional[List[str]] = None,
    paths: Optional[List[str]] = None,
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    """存储图片到会话并返回标识符

    Args:
        urls: 图片 URL 列表
        paths: 本地图片文件路径列表（相对于 data/ 目录）
        session: 当前会话（自动注入）

    Returns:
        工具执行结果，包含图片标识符
    """
    if not session:
        return fail(
            "无法获取会话信息，请稍后重试",
            error="Missing session"
        )

    urls = urls or []
    paths = paths or []

    if not urls and not paths:
        return fail("请至少提供 urls 或 paths 中的一个参数")

    total_count = len(urls) + len(paths)
    if total_count > 10:
        logger.warning(f"请求存储 {total_count} 张图片，限制为 10 张")
        if len(urls) >= 10:
            urls = urls[:10]
            paths = []
        else:
            paths = paths[:10 - len(urls)]

    attempted_count = len(urls) + len(paths)
    identifiers = []
    failed_items = []

    # 处理 URL
    for i, url in enumerate(urls, 1):
        url = url.strip()
        if not url:
            continue
        logger.debug(f"下载第 {i}/{len(urls)} 张图片: {url[:80]}...")
        image_data = await _download_image_to_base64(url)
        if image_data:
            identifier = await session.store_ai_image(image_data, url=url)
            identifiers.append(identifier)
            logger.info(f"URL 图片 {i} 下载成功: {identifier}")
        else:
            failed_items.append(url)
            logger.warning(f"URL 图片 {i} 下载失败: {url}")

    # 处理本地路径
    for i, path in enumerate(paths, 1):
        path = path.strip()
        if not path:
            continue
        logger.debug(f"读取本地图片 {i}/{len(paths)}: {path}")
        image_data = _read_local_image(path)
        if image_data:
            identifier = await session.store_ai_image(image_data)
            identifiers.append(identifier)
            logger.info(f"本地图片 {i} 读取成功: {identifier}")
        else:
            failed_items.append(path)
            logger.warning(f"本地图片 {i} 读取失败: {path}")

    if not identifiers:
        return fail(
            "所有图片存储失败，请检查 URL 或文件路径是否有效",
            error="All sources failed"
        )

    # 构建返回消息
    result_lines = [f"已准备 {len(identifiers)} 张图片："]
    for identifier in identifiers:
        result_lines.append(identifier)

    failed_count = attempted_count - len(identifiers)
    if failed_count > 0:
        result_lines.append(f"\n⚠️ {failed_count} 张图片存储失败")

    result_lines.append("\n💡 在你的回复中包含上述标识符，用户就能看到图片")

    return ok(
        "\n".join(result_lines),
        metadata={
            "identifiers": identifiers,
            "success_count": len(identifiers),
            "failed_count": failed_count,
        }
    )
