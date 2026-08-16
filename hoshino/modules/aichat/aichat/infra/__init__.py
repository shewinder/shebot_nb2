"""aichat 基础设施包

统一底座：错误模型、日志上下文/脱敏、LLM Gateway。
本包内所有模块禁止 import hoshino（保持可独立测试）。
"""
from .errors import (
    AppError,
    LLMAuthError,
    LLMError,
    LLMNetworkError,
    LLMParseError,
    LLMRateLimitedError,
    LLMRequestError,
    LLMTimeoutError,
    LLMUpstreamError,
    Result,
)
from .logging import log_context, log_tag, sanitize, sanitize_text
from .metrics import Metrics, metrics
from .llm_gateway import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_READ_TIMEOUT,
    LLMGateway,
    LLMResult,
    close_all_gateways,
    get_gateway,
)

__all__ = [
    # errors
    "AppError",
    "LLMError",
    "LLMNetworkError",
    "LLMTimeoutError",
    "LLMRateLimitedError",
    "LLMAuthError",
    "LLMRequestError",
    "LLMUpstreamError",
    "LLMParseError",
    "Result",
    # logging
    "log_context",
    "log_tag",
    "sanitize",
    "sanitize_text",
    # metrics
    "Metrics",
    "metrics",
    # llm_gateway
    "LLMGateway",
    "LLMResult",
    "get_gateway",
    "close_all_gateways",
    "DEFAULT_CONNECT_TIMEOUT",
    "DEFAULT_READ_TIMEOUT",
    "DEFAULT_MAX_RETRIES",
]
