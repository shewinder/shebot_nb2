"""
AI 工具：批量下载并发送图片
下载指定 URL 的图片并存储到会话中，返回标识符供 AI 引用
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
        resp = await aiohttpx.get(image_url)
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


@tool_registry.register(
    name="send_images",
    description="""下载指定 URL 的图片并发送给用户。

用于需要直接展示图片的场景，如 Pixiv 作品、表情包、截图等。
支持批量下载多个图片，适合展示排行榜、作品集等。

## 使用方式

1. 获取图片 URL 列表
2. 调用本工具下载图片
3. 工具返回图片标识符（如 <ai_image_1>, <ai_image_2>）
4. 在你的回复中包含这些标识符，系统会自动发送图片

## 示例

### 单张图片
```python
send_images(urls=["https://example.com/image.jpg"])
# 返回："已准备 1 张图片：<ai_image_1>"
# 你回复："这是图片 <ai_image_1>"
```

### 多张图片
```python
send_images(urls=["https://example.com/1.jpg", "https://example.com/2.jpg"])
# 返回："已准备 2 张图片：<ai_image_1> <ai_image_2>"
# 你回复："图片1 <ai_image_1> 图片2 <ai_image_2>"
```

## 注意事项

- 建议一次最多 5-10 张图片，避免下载时间过长
- 图片过大会自动跳过（限制 10MB）
- 下载失败会返回错误信息，但成功的图片仍会返回标识符
- 必须在你的回复中包含标识符，用户才能看到图片""",
    parameters={
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "图片 URL 列表，支持多张图片批量下载"
            }
        },
        "required": ["urls"]
    },
)
async def send_images(
    urls: List[str],
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    """
    批量下载图片并返回标识符
    
    Args:
        urls: 图片 URL 列表
        session: 当前会话（自动注入）
        
    Returns:
        工具执行结果，包含图片标识符
    """
    if not session:
        return fail(
            "无法获取会话信息，请稍后重试",
            error="Missing session"
        )
    
    if not urls:
        return fail("请提供至少一个图片 URL")
    
    # 限制数量
    if len(urls) > 10:
        logger.warning(f"请求下载 {len(urls)} 张图片，限制为 10 张")
        urls = urls[:10]
    
    logger.info(f"准备下载 {len(urls)} 张图片")
    
    identifiers = []
    failed_urls = []
    
    for i, url in enumerate(urls, 1):
        url = url.strip()
        if not url:
            continue
        
        logger.debug(f"下载第 {i}/{len(urls)} 张图片: {url[:80]}...")
        
        image_data = await _download_image_to_base64(url)
        if image_data:
            identifier = session.store_ai_image(image_data)
            identifiers.append(identifier)
            logger.info(f"图片 {i} 下载成功: {identifier}")
        else:
            logger.warning(f"图片 {i} 下载失败: {url}")
    
    if not identifiers:
        return fail(
            f"所有图片下载失败，请检查 URL 是否有效",
            error=f"Failed URLs: {failed_urls[:3]}"
        )
    
    # 构建返回消息
    result_lines = [f"已准备 {len(identifiers)} 张图片："]
    for identifier in identifiers:
        result_lines.append(identifier)
    
    if failed_urls:
        result_lines.append(f"\n⚠️ {len(failed_urls)} 张图片下载失败")
    
    result_lines.append("\n💡 在你的回复中包含上述标识符，用户就能看到图片")
    
    return ok(
        "\n".join(result_lines),
        metadata={
            "identifiers": identifiers,
            "success_count": len(identifiers),
            "failed_count": len(failed_urls),
            "failed_urls": failed_urls[:3]  # 只保留前3个失败的
        }
    )
