"""
AI 工具：网页搜索
使用阿里云百炼 IQS (信息查询服务) 搜索网页内容
文档: https://help.aliyun.com/zh/document_detail/2883041.html
"""
from typing import Any, Dict, List, Optional

from loguru import logger

from hoshino.util import aiohttpx

from ..registry import tool_registry, ok, fail
from ...config import Config

# 加载配置
conf = Config.get_instance('aichat')

# IQS API 配置
IQS_API_BASE = "https://cloud-iqs.aliyuncs.com"


async def _search_with_iqs(
    query: str,
    api_key: str,
    engine_type: str = "Generic",
    time_range: str = "NoLimit",
    category: Optional[str] = None,
    include_main_text: bool = False,
    include_summary: bool = False,
) -> Dict[str, Any]:
    """
    调用阿里云 IQS 搜索 API
    
    Args:
        query: 搜索关键词
        api_key: IQS API Key
        engine_type: 搜索引擎类型 (Generic/GenericAdvanced/LiteAdvanced)
        time_range: 时间范围 (OneDay/OneWeek/OneMonth/OneYear/NoLimit)
        category: 搜索分类 (finance/law/medical/internet/tax/news_province/news_center)
        include_main_text: 是否返回网页正文
        include_summary: 是否返回 AI 摘要 (收费)
    
    Returns:
        API 响应数据
    """
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


def _format_search_results(data: Dict[str, Any], include_main_text: bool, include_summary: bool) -> str:
    """
    格式化搜索结果为文本
    
    Args:
        data: IQS API 返回的数据
        include_main_text: 是否包含网页正文
        include_summary: 是否包含 AI 摘要
    
    Returns:
        格式化后的文本
    """
    page_items = data.get("pageItems", [])
    if not page_items:
        return "未找到相关搜索结果。"
    
    parts = []
    parts.append(f"搜索到 {len(page_items)} 条结果：\n")
    
    for i, item in enumerate(page_items[:10], 1):  # 最多显示10条
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
            # 清理 snippet 中的多余空白
            snippet = " ".join(snippet.split())
            parts.append(f"   摘要: {snippet}")
        
        # 如果开启了 summary 且存在，显示 AI 摘要
        if include_summary:
            summary = item.get("summary")
            if summary:
                summary = " ".join(summary.split())
                parts.append(f"   AI摘要: {summary}")
        
        # 如果开启了 main_text 且存在，显示正文
        if include_main_text:
            main_text = item.get("mainText") or item.get("markdownText")
            if main_text:
                # 截取前500字符
                main_text = main_text[:500].strip()
                parts.append(f"   正文: {main_text}...")
        
        if link:
            parts.append(f"   链接: {link}")
        
        parts.append("")  # 空行分隔
    
    return "\n".join(parts)


@tool_registry.register(
    name="web_search",
    description="""【首选】搜索网页获取实时信息。

使用阿里云百炼 IQS 搜索引擎，返回相关网页的标题、摘要和链接。
适合查询新闻、知识、最新动态等需要实时信息的场景。

使用优先级（重要）：
1. 当需要搜索信息但不确定具体链接时 → 优先使用 web_search（本工具）
2. 当已知具体 URL 想获取内容时 → 使用 web_fetch
3. 当 web_search 和 web_fetch 都无法满足需求时（如页面需要 JavaScript 渲染、需要模拟点击等） → 最后考虑使用浏览器工具

注意事项：
- 搜索关键词应简洁明确，建议不超过30个字符
- 如需特定时间范围的信息，可使用 time_range 参数
- 如需更详细内容，可开启 include_main_text 获取网页正文""",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，建议简洁明确，不超过30个字符"
            },
            "engine_type": {
                "type": "string",
                "enum": ["Generic", "GenericAdvanced", "LiteAdvanced"],
                "description": "搜索引擎类型: Generic(标准,返回10条)/GenericAdvanced(增强,约50条,收费)/LiteAdvanced(极速版)"
            },
            "time_range": {
                "type": "string",
                "enum": ["OneDay", "OneWeek", "OneMonth", "OneYear", "NoLimit"],
                "description": "时间范围: OneDay(1天)/OneWeek(1周)/OneMonth(1月)/OneYear(1年)/NoLimit(不限)"
            },
            "include_main_text": {
                "type": "boolean",
                "description": "是否返回网页正文内容（更长更详细，默认false）"
            },
            "include_summary": {
                "type": "boolean",
                "description": "是否返回AI生成的增强摘要（额外收费，默认false）"
            }
        },
        "required": ["query"]
    },
)
async def web_search(
    query: str,
    engine_type: str = "Generic",
    time_range: str = "NoLimit",
    include_main_text: bool = False,
    include_summary: bool = False,
) -> Dict[str, Any]:
    """
    搜索网页获取信息
    
    Args:
        query: 搜索关键词
        engine_type: 搜索引擎类型
        time_range: 时间范围
        include_main_text: 是否包含网页正文
        include_summary: 是否包含 AI 摘要
    
    Returns:
        工具执行结果
    """
    try:
        # 获取 API Key
        api_key = getattr(conf, 'iqs_api_key', '')
        if not api_key:
            return fail("搜索服务未配置，请联系管理员设置阿里云 IQS API Key")
        
        # 参数校验
        if not query or not query.strip():
            return fail("搜索关键词不能为空")
        
        query = query.strip()
        if len(query) > 500:
            query = query[:500]
            logger.warning(f"搜索关键词过长，已截断至500字符")
        
        # 调用搜索 API
        result = await _search_with_iqs(
            query=query,
            api_key=api_key,
            engine_type=engine_type,
            time_range=time_range,
            include_main_text=include_main_text,
            include_summary=include_summary,
        )
        
        if not result.get("success"):
            error = result.get("error", "未知错误")
            return fail(f"搜索失败: {error}")
        
        data = result.get("data", {})
        request_id = data.get("requestId", "")
        page_items = data.get("pageItems", [])
        
        if not page_items:
            return ok("未找到相关搜索结果。", metadata={"query": query, "request_id": request_id})
        
        # 格式化结果
        formatted_content = _format_search_results(
            data, include_main_text, include_summary
        )
        
        # 提取链接列表用于元数据
        links = [item.get("link", "") for item in page_items if item.get("link")]
        
        logger.info(f"搜索成功: query={query}, 结果数={len(page_items)}, request_id={request_id}")
        
        return ok(
            formatted_content,
            metadata={
                "query": query,
                "result_count": len(page_items),
                "request_id": request_id,
                "engine_type": engine_type,
                "links": links[:5],  # 只保留前5个链接
            }
        )
        
    except Exception as e:
        logger.exception(f"搜索失败: {e}")
        return fail(f"搜索失败: {str(e)}", error=str(e))
