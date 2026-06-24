"""
阿里云百炼 IQS (信息查询服务) Provider
https://help.aliyun.com/zh/document_detail/2883041.html
"""
import os
from typing import Any, Dict, Optional

from loguru import logger

from hoshino.util import aiohttpx
from ...registry import ok, fail

IQS_API_BASE = "https://cloud-iqs.aliyuncs.com"

PROVIDER = {
    "name": "iqs",
    "label": "IQS (阿里云百炼)",
    "key_env": "IQS_API_KEY",
    "description": """【首选】搜索网页获取实时信息。

使用阿里云百炼 IQS 搜索引擎，返回相关网页的标题、摘要和链接。
适合查询新闻、知识、最新动态等需要实时信息的场景。

使用优先级（重要）：
1. 当需要搜索信息但不确定具体链接时 → 优先使用 web_search（本工具）
2. 当已知具体 URL 想获取内容时 → 使用 web_fetch
3. 当 web_search 和 web_fetch 都无法满足需求时 → 最后考虑使用浏览器工具""",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，建议简洁明确，不超过500个字符"
            },
            "engine_type": {
                "type": "string",
                "enum": ["Generic", "GenericAdvanced", "LiteAdvanced"],
                "description": "引擎类型: Generic(标准,10条)/GenericAdvanced(增强,约50条,收费)/LiteAdvanced(极速版)",
            },
            "time_range": {
                "type": "string",
                "enum": ["OneDay", "OneWeek", "OneMonth", "OneYear", "NoLimit"],
                "description": "时间范围: OneDay(1天)/OneWeek(1周)/OneMonth(1月)/OneYear(1年)/NoLimit(不限)",
            },
            "include_main_text": {
                "type": "boolean",
                "description": "是否返回网页正文内容（默认false）",
                "default": False,
            },
            "include_summary": {
                "type": "boolean",
                "description": "是否返回AI生成的增强摘要（额外收费，默认false）",
                "default": False,
            },
        },
        "required": ["query"]
    },
}


async def _search(
    query: str,
    api_key: str,
    engine_type: str = "Generic",
    time_range: str = "NoLimit",
    category: Optional[str] = None,
    include_main_text: bool = False,
    include_summary: bool = False,
) -> Dict[str, Any]:
    """调用阿里云 IQS 搜索 API"""
    url = f"{IQS_API_BASE}/search/unified"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    contents = {
        "mainText": include_main_text,
        "markdownText": False,
        "richMainBody": False,
        "summary": include_summary,
        "rerankScore": True,
    }

    payload: Dict[str, Any] = {
        "query": query,
        "engineType": engine_type,
        "timeRange": time_range,
        "contents": contents,
    }

    if category:
        payload["category"] = category

    try:
        resp = await aiohttpx.post(url, headers=headers, json=payload)
        if not resp.ok:
            error_text = resp.text if hasattr(resp, 'text') else str(resp)
            logger.error(f"IQS 搜索失败: {resp.status_code}, {error_text[:200]}")
            return {"success": False, "error": f"HTTP {resp.status_code}: {error_text[:200]}"}

        data = resp.json if hasattr(resp, 'json') else await resp.json()
        return {"success": True, "data": data}

    except Exception as e:
        logger.exception(f"IQS 搜索异常: {e}")
        return {"success": False, "error": str(e)}


def _format(data: Dict[str, Any], include_main_text: bool, include_summary: bool) -> str:
    """格式化 IQS 搜索结果为文本"""
    page_items = data.get("pageItems", [])
    if not page_items:
        return "未找到相关搜索结果。"

    parts = []
    parts.append(f"搜索到 {len(page_items)} 条结果：\n")

    for i, item in enumerate(page_items[:10], 1):
        title = item.get("title", "无标题")
        link = item.get("link", "")
        snippet = item.get("snippet", "")
        hostname = item.get("hostname", "")
        published_time = item.get("publishedTime", "")

        parts.append(f"{i}. {title}")
        if hostname:
            parts.append(f"   来源: {hostname}")
        if published_time:
            parts.append(f"   时间: {published_time}")
        if snippet:
            snippet = " ".join(snippet.split())
            parts.append(f"   摘要: {snippet}")

        if include_summary:
            summary = item.get("summary")
            if summary:
                summary = " ".join(summary.split())
                parts.append(f"   AI摘要: {summary}")

        if include_main_text:
            main_text = item.get("mainText") or item.get("markdownText")
            if main_text:
                main_text = main_text[:500].strip()
                parts.append(f"   正文: {main_text}...")

        if link:
            parts.append(f"   链接: {link}")

        parts.append("")

    return "\n".join(parts)


async def tool_fn(
    query: str,
    engine_type: str = "Generic",
    time_range: str = "NoLimit",
    include_main_text: bool = False,
    include_summary: bool = False,
) -> Dict[str, Any]:
    """IQS 搜索 tool 入口"""
    if not query or not query.strip():
        return fail("搜索关键词不能为空")

    query = query.strip()[:500]

    api_key = os.getenv("IQS_API_KEY", "")
    if not api_key:
        return fail("搜索服务未配置 (IQS)，请设置 IQS_API_KEY")

    result = await _search(
        query=query, api_key=api_key,
        engine_type=engine_type, time_range=time_range,
        include_main_text=include_main_text, include_summary=include_summary,
    )

    if not result["success"]:
        return fail(f"搜索失败 (IQS): {result['error']}")

    data = result["data"]
    request_id = data.get("requestId", "")
    page_items = data.get("pageItems", [])

    if not page_items:
        return ok("未找到相关搜索结果。", metadata={"query": query, "request_id": request_id, "provider": "iqs"})

    content = _format(data, include_main_text, include_summary)
    links = [item.get("link", "") for item in page_items if item.get("link")]

    logger.info(f"[IQS] 搜索成功: query={query}, 结果数={len(page_items)}, request_id={request_id}")

    return ok(content, metadata={
        "query": query, "result_count": len(page_items),
        "request_id": request_id, "engine_type": engine_type,
        "links": links[:5], "provider": "iqs",
    })
