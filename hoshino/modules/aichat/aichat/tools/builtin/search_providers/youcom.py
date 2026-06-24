"""
You.com Search API Provider
https://you.com/docs/guides/search
"""
import os
from typing import Any, Dict, List, Optional

from loguru import logger

from hoshino.util import aiohttpx
from ...registry import ok, fail

YOUCOM_API_BASE = "https://ydc-index.io"

PROVIDER = {
    "name": "youcom",
    "label": "You.com",
    "key_env": "YOUCOM_API_KEY",
    "description": """【首选】搜索网页获取实时信息。

使用 You.com Search API，返回相关网页的标题、摘要和链接。
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
            "count": {
                "type": "integer",
                "description": "返回结果数量，默认10，最大100",
                "default": 10,
            },
            "freshness": {
                "type": "string",
                "enum": ["day", "week", "month", "year", "nolimit"],
                "description": "时间范围: day(1天)/week(1周)/month(1月)/year(1年)/nolimit(不限)",
            },
            "country": {
                "type": "string",
                "description": "国家代码 (CN/US/JP)，不填不限制"
            },
            "language": {
                "type": "string",
                "description": "语言代码 (zh/en/ja)，不填自动检测"
            },
            "include_domains": {
                "type": "string",
                "description": "限定域名，逗号分隔，只搜这些域名"
            },
            "exclude_domains": {
                "type": "string",
                "description": "排除域名，逗号分隔，跳过这些域名"
            },
            "livecrawl": {
                "type": "boolean",
                "description": "是否抓取网页全文 (默认false)。开启后返回完整HTML/Markdown",
                "default": False,
            },
        },
        "required": ["query"]
    },
}


async def _search(
    query: str,
    api_key: str,
    count: int = 10,
    freshness: Optional[str] = None,
    country: Optional[str] = None,
    language: Optional[str] = None,
    livecrawl: bool = False,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """调用 You.com Search API"""
    url = f"{YOUCOM_API_BASE}/v1/search"
    headers = {
        "X-API-KEY": api_key,
        "Accept": "application/json",
    }

    params: Dict[str, Any] = {
        "query": query,
        "count": count,
    }

    if freshness:
        params["freshness"] = freshness
    if country:
        params["country"] = country
    if language:
        params["language"] = language
    if livecrawl:
        params["livecrawl"] = "all"
    if include_domains:
        params["include_domains"] = ",".join(include_domains)
    if exclude_domains:
        params["exclude_domains"] = ",".join(exclude_domains)

    try:
        resp = await aiohttpx.get(url, headers=headers, params=params)
        if not resp.ok:
            error_text = resp.text if hasattr(resp, 'text') else str(resp)
            logger.error(f"You.com 搜索失败: {resp.status_code}, {error_text[:200]}")
            return {"success": False, "error": f"HTTP {resp.status_code}: {error_text[:200]}"}

        data = resp.json if hasattr(resp, 'json') else await resp.json()
        return {"success": True, "data": data}

    except Exception as e:
        logger.exception(f"You.com 搜索异常: {e}")
        return {"success": False, "error": str(e)}


def _format(data: Dict[str, Any], livecrawl: bool) -> str:
    """格式化 You.com 搜索结果为文本"""
    web_results = data.get("results", {}).get("web", [])
    if not web_results:
        return "未找到相关搜索结果。"

    parts = []
    parts.append(f"搜索到 {len(web_results)} 条结果：\n")

    for i, item in enumerate(web_results[:10], 1):
        title = item.get("title", "无标题")
        url = item.get("url", "")
        description = item.get("description", "")
        page_age = item.get("page_age", "")
        snippets = item.get("snippets", [])

        parts.append(f"{i}. {title}")
        if url:
            parts.append(f"   链接: {url}")
        if page_age:
            parts.append(f"   时间: {page_age}")
        if description:
            description = " ".join(description.split())
            parts.append(f"   描述: {description}")

        if livecrawl:
            contents = item.get("contents", {})
            if contents:
                html_content = contents.get("html", "")
                markdown_content = contents.get("markdown", "")
                full_content = markdown_content or html_content
                full_content = full_content[:1000].strip()
                parts.append(f"   全文: {full_content}...")
        else:
            if snippets:
                parts.append(f"   片段: ")
                for snippet in snippets[:3]:
                    snippet = " ".join(snippet.split())
                    parts.append(f"      {snippet}")

        parts.append("")

    return "\n".join(parts)


async def tool_fn(
    query: str,
    count: int = 10,
    freshness: str = "nolimit",
    country: Optional[str] = None,
    language: Optional[str] = None,
    include_domains: Optional[str] = None,
    exclude_domains: Optional[str] = None,
    livecrawl: bool = False,
) -> Dict[str, Any]:
    """You.com 搜索 tool 入口"""
    if not query or not query.strip():
        return fail("搜索关键词不能为空")

    query = query.strip()[:500]

    api_key = os.getenv("YOUCOM_API_KEY", "")
    if not api_key:
        return fail("搜索服务未配置 (You.com)，请设置 YOUCOM_API_KEY")

    freshness_value = freshness if freshness and freshness != "nolimit" else None
    include_domains_list = [d.strip() for d in include_domains.split(",") if d.strip()] if include_domains else None
    exclude_domains_list = [d.strip() for d in exclude_domains.split(",") if d.strip()] if exclude_domains else None

    result = await _search(
        query=query, api_key=api_key, count=count,
        freshness=freshness_value, country=country, language=language,
        livecrawl=livecrawl,
        include_domains=include_domains_list,
        exclude_domains=exclude_domains_list,
    )

    if not result["success"]:
        return fail(f"搜索失败 (You.com): {result['error']}")

    data = result["data"]
    search_uuid = data.get("metadata", {}).get("search_uuid", "")
    web_results = data.get("results", {}).get("web", [])

    if not web_results:
        return ok("未找到相关搜索结果。", metadata={"query": query, "search_uuid": search_uuid, "provider": "youcom"})

    content = _format(data, livecrawl)
    links = [item.get("url", "") for item in web_results if item.get("url")]

    logger.info(f"[You.com] 搜索成功: query={query}, 结果数={len(web_results)}, search_uuid={search_uuid}")

    return ok(content, metadata={
        "query": query, "result_count": len(web_results),
        "search_uuid": search_uuid, "links": links[:5], "provider": "youcom",
    })
