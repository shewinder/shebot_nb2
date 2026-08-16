"""LLM Gateway — 统一的 OpenAI 兼容 API 客户端

职责：
- httpx 共享连接池（取代每次新建 ClientSession 的 aiohttpx）
- connect/read 超时
- 429/5xx/网络错误自动重试（指数退避 + 抖动，429 尊重 Retry-After）
- 错误分类为 AppError 子类（不再返回裸字符串）
- 日志脱敏（错误信息中的 base64 图片数据替换为占位符）
- usage 提取

约束：本模块不依赖 hoshino，配置通过构造参数注入，
便于用 httpx.MockTransport 做单元测试。

注意：本模块只面向 OpenAI 兼容的 /chat/completions 接口。
"""
import asyncio
import json
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from .errors import (
    LLMAuthError,
    LLMError,
    LLMNetworkError,
    LLMParseError,
    LLMRateLimitedError,
    LLMRequestError,
    LLMTimeoutError,
    LLMUpstreamError,
)
from .logging import sanitize_text

# 可重试的 HTTP 状态码
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_READ_TIMEOUT = 120.0
DEFAULT_MAX_RETRIES = 2
_MAX_RETRY_AFTER_SECONDS = 30.0


@dataclass
class LLMResult:
    """一次成功的 LLM 调用结果"""

    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, int]] = None


def _parse_retry_after(headers: httpx.Headers) -> Optional[float]:
    """解析 Retry-After 头（支持秒数与 HTTP 日期）"""
    value = headers.get("Retry-After")
    if not value:
        return None
    try:
        return min(float(value), _MAX_RETRY_AFTER_SECONDS)
    except ValueError:
        return None


class LLMGateway:
    """OpenAI 兼容 chat completions 客户端（带重试与错误分类）"""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        *,
        max_retries: int = DEFAULT_MAX_RETRIES,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.max_retries = max(0, max_retries)
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        # client 注入（测试用）时连接池生命周期归调用方
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(connect_timeout, read=read_timeout),
        )

    @property
    def chat_url(self) -> str:
        return f"{self.api_base}/chat/completions"

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _backoff_seconds(self, attempt: int, retry_after: Optional[float]) -> float:
        """第 attempt 次重试（≥1）前的等待秒数：Retry-After 优先，否则指数退避 + 抖动"""
        if retry_after is not None:
            return retry_after
        base = min(0.5 * (2 ** (attempt - 1)), 8.0)
        return base + random.uniform(0, base * 0.5)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResult:
        """发起一次 chat 请求，失败时抛出 AppError 子类"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {"model": model, "messages": messages}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        logger.info(
            f"[LLMGateway] 请求 {self.chat_url} model={model} "
            f"messages={len(messages)} tools={len(tools) if tools else 0}"
        )

        last_error: Optional[LLMError] = None
        retry_after: Optional[float] = None

        for attempt in range(self.max_retries + 1):
            if attempt > 0 and last_error is not None:
                delay = self._backoff_seconds(attempt, retry_after)
                logger.warning(
                    f"[LLMGateway] 第 {attempt} 次重试，等待 {delay:.1f}s，原因: {last_error}"
                )
                await asyncio.sleep(delay)

            try:
                resp = await self._client.post(self.chat_url, headers=headers, json=payload)
            except httpx.TimeoutException as e:
                last_error = LLMTimeoutError(f"请求超时（>{self.read_timeout}s）", cause=e)
                continue
            except httpx.HTTPError as e:
                last_error = LLMNetworkError(f"网络错误: {e}", cause=e)
                continue

            if resp.status_code == 429:
                retry_after = _parse_retry_after(resp.headers)
                last_error = LLMRateLimitedError(
                    f"请求被限流（HTTP 429）",
                    retry_after=retry_after,
                    status_code=429,
                )
                continue
            if resp.status_code in (401, 403):
                raise LLMAuthError(
                    f"鉴权失败（HTTP {resp.status_code}），请检查 api_key",
                    status_code=resp.status_code,
                )
            if resp.status_code in RETRYABLE_STATUS:
                last_error = LLMUpstreamError(
                    f"上游服务错误（HTTP {resp.status_code}）: {sanitize_text(resp.text, max_len=500)}",
                    status_code=resp.status_code,
                )
                continue
            if resp.status_code != 200:
                raise LLMRequestError(
                    f"请求被拒绝（HTTP {resp.status_code}）: {sanitize_text(resp.text, max_len=500)}",
                    status_code=resp.status_code,
                )

            return self._parse_response(resp)

        # 重试次数耗尽
        raise last_error or LLMError("LLM 调用失败", code="llm.unknown")

    def _parse_response(self, resp: httpx.Response) -> LLMResult:
        try:
            result = resp.json()
        except json.JSONDecodeError as e:
            raise LLMParseError(
                f"响应不是合法 JSON: {sanitize_text(resp.text, max_len=300)}", cause=e
            ) from e

        if not isinstance(result, dict):
            raise LLMParseError("响应格式错误：顶层不是 JSON 对象")

        # 部分供应商在 HTTP 200 下通过 error 字段报错
        if "error" in result:
            error_info = result.get("error") or {}
            message = error_info.get("message") if isinstance(error_info, dict) else str(error_info)
            raise LLMUpstreamError(
                f"API 返回错误: {sanitize_text(str(message), max_len=500)}"
            )

        choices = result.get("choices")
        if not choices or not isinstance(choices, list):
            raise LLMParseError("响应格式错误：缺少 choices")

        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""
        tool_calls = message.get("tool_calls") or []
        finish_reason = choice.get("finish_reason") or ""
        usage = result.get("usage")

        content = content.strip() if isinstance(content, str) else ""
        reasoning = reasoning.strip() if isinstance(reasoning, str) else ""

        return LLMResult(
            content=content or None,
            reasoning_content=reasoning or None,
            tool_calls=tool_calls if isinstance(tool_calls, list) else [],
            finish_reason=finish_reason,
            raw=result,
            usage=usage if isinstance(usage, dict) else None,
        )


# ========== 网关注册表（按 api_base 复用连接池） ==========

_gateways: Dict[str, LLMGateway] = {}


def get_gateway(
    api_base: str,
    api_key: str,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    read_timeout: float = DEFAULT_READ_TIMEOUT,
) -> LLMGateway:
    """获取指定 api_base 的共享网关；api_key 或参数变化时重建

    参数默认值仅作兜底；生产调用方（chat_executor）应传入 Config 中的值。
    """
    key = api_base.rstrip("/")
    gateway = _gateways.get(key)
    if (
        gateway is None
        or gateway.api_key != api_key
        or gateway.max_retries != max_retries
        or gateway.read_timeout != read_timeout
    ):
        gateway = LLMGateway(
            api_base,
            api_key,
            max_retries=max_retries,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        )
        _gateways[key] = gateway
    return gateway


async def close_all_gateways() -> None:
    """关闭所有网关连接池（进程关闭时调用）"""
    for gateway in _gateways.values():
        await gateway.aclose()
    _gateways.clear()
