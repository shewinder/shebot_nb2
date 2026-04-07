"""
AI 工具：获取指定 URL 内容
直接访问 URL 获取 JSON 或文本内容
"""
from typing import Any, Dict, Optional

from loguru import logger

from hoshino.util import aiohttpx

from ..registry import tool_registry, ok, fail


@tool_registry.register(
    name="fetch_url",
    description="""获取指定 URL 的内容（JSON 或文本）。

用于已知具体 URL 需要获取内容的场景，如 API 调用、网页抓取等。

使用优先级：
1. 当需要搜索信息但不确定具体链接时 → 使用 web_search
2. 当已知具体 URL 想获取内容时 → 优先使用 fetch_url（本工具）

注意事项：
- 仅支持 GET 请求
- 适合 REST API 调用
- 如果返回 JSON，结果会格式化展示
- 如果返回文本/HTML，会截取前 5000 字符""",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要访问的完整 URL"
            },
            "headers": {
                "type": "object",
                "description": "可选的请求头（如 User-Agent、Authorization 等）"
            },
            "timeout": {
                "type": "integer",
                "description": "超时时间（秒），默认 30"
            }
        },
        "required": ["url"]
    },
)
async def fetch_url(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    获取指定 URL 的内容
    
    Args:
        url: 目标 URL
        headers: 请求头
        timeout: 超时时间
        
    Returns:
        工具执行结果
    """
    try:
        if not url or not url.strip():
            return fail("URL 不能为空")
        
        url = url.strip()
        
        # 简单的 URL 格式检查
        if not url.startswith(('http://', 'https://')):
            return fail("URL 必须以 http:// 或 https:// 开头")
        
        # 准备请求头
        request_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        if headers:
            request_headers.update(headers)
        
        logger.info(f"Fetching URL: {url}")
        
        # 发送请求
        resp = await aiohttpx.get(url, headers=request_headers, timeout=timeout)
        
        if not resp.ok:
            return fail(f"请求失败: HTTP {resp.status_code}", error=f"HTTP {resp.status_code}")
        
        content_type = resp.headers.get('content-type', '').lower()
        text_content = resp.text if hasattr(resp, 'text') else await resp.text()
        
        # 判断是否是 JSON
        is_json = 'application/json' in content_type or text_content.strip().startswith(('{', '['))
        
        if is_json:
            try:
                import json
                data = json.loads(text_content)
                # 格式化 JSON 以便展示
                formatted = json.dumps(data, ensure_ascii=False, indent=2)
                # TODO: 临时放宽到 50KB，后续需要优化大数据量处理
                if len(formatted) > 50000:
                    formatted = formatted[:50000] + "\n... (内容已截断，共 " + str(len(formatted)) + " 字符)"
                
                return ok(
                    f"JSON 数据获取成功:\n```json\n{formatted}\n```",
                    metadata={
                        "url": url,
                        "content_type": "json",
                        "size": len(text_content)
                    }
                )
            except json.JSONDecodeError:
                # 不是有效的 JSON，按文本处理
                pass
        
        # 文本内容处理（TODO: 临时放宽到 50KB）
        if len(text_content) > 50000:
            text_content = text_content[:50000] + "\n... (内容已截断，共 " + str(len(text_content)) + " 字符)"
        
        return ok(
            f"内容获取成功:\n```\n{text_content}\n```",
            metadata={
                "url": url,
                "content_type": content_type or "text",
                "size": len(text_content)
            }
        )
        
    except Exception as e:
        logger.exception(f"获取 URL 失败: {e}")
        return fail(f"获取失败: {str(e)}", error=str(e))
