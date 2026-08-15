"""统一的错误与结果模型

全插件唯一的错误类型体系。工具调用、MCP、LLM API 各层最终收敛到这里，
上层只依赖 AppError 的 code / retryable 做差异化处理，不再解析字符串。

约束：本模块只依赖标准库，禁止 import hoshino。
"""
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class AppError(Exception):
    """应用错误基类

    Attributes:
        code: 机器可读错误码（如 "llm.rate_limited"），供日志与监控分类
        retryable: 是否适合自动重试
        status_code: 关联的 HTTP 状态码（网络层错误时提供）
        cause: 原始异常（如有）
    """

    def __init__(
        self,
        message: str,
        *,
        code: str,
        retryable: bool = False,
        status_code: Optional[int] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.cause = cause

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


# ========== LLM API 错误层级 ==========


class LLMError(AppError):
    """LLM API 调用错误基类"""

    def __init__(self, message: str, **kwargs) -> None:
        kwargs.setdefault("code", "llm.error")
        super().__init__(message, **kwargs)


class LLMNetworkError(LLMError):
    """连接/传输层错误（DNS、连接拒绝、TLS 等）"""

    def __init__(self, message: str, **kwargs) -> None:
        kwargs.setdefault("code", "llm.network")
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class LLMTimeoutError(LLMError):
    """请求超时"""

    def __init__(self, message: str, **kwargs) -> None:
        kwargs.setdefault("code", "llm.timeout")
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class LLMRateLimitedError(LLMError):
    """限流（HTTP 429）"""

    def __init__(self, message: str, retry_after: Optional[float] = None, **kwargs) -> None:
        kwargs.setdefault("code", "llm.rate_limited")
        kwargs.setdefault("retryable", True)
        kwargs.setdefault("status_code", 429)
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class LLMAuthError(LLMError):
    """鉴权失败（HTTP 401/403），不应重试"""

    def __init__(self, message: str, **kwargs) -> None:
        kwargs.setdefault("code", "llm.auth")
        super().__init__(message, **kwargs)


class LLMRequestError(LLMError):
    """请求被拒绝（其余 4xx / 参数错误），不应重试"""

    def __init__(self, message: str, **kwargs) -> None:
        kwargs.setdefault("code", "llm.request")
        super().__init__(message, **kwargs)


class LLMUpstreamError(LLMError):
    """上游服务错误（HTTP 5xx / 响应体携带 error）"""

    def __init__(self, message: str, **kwargs) -> None:
        kwargs.setdefault("code", "llm.upstream")
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class LLMParseError(LLMError):
    """响应解析失败（非法 JSON / 结构不符）"""

    def __init__(self, message: str, **kwargs) -> None:
        kwargs.setdefault("code", "llm.parse")
        super().__init__(message, **kwargs)


# ========== 通用 Result ==========


class Result(Generic[T]):
    """成功/失败二选一的结果容器

    用于需要显式传播错误的同步/异步边界，替代 (value, error) 元组。
    """

    _UNSET = object()

    def __init__(self, value: T = _UNSET, error: Optional[AppError] = None) -> None:
        if value is not Result._UNSET and error is not None:
            raise ValueError("Result 不能同时提供 value 和 error")
        if value is Result._UNSET and error is None:
            raise ValueError("Result 必须提供 value 或 error 之一")
        self._value = None if value is Result._UNSET else value
        self._error = error

    @staticmethod
    def success(value: T) -> "Result[T]":
        return Result(value=value)

    @staticmethod
    def failure(error: AppError) -> "Result[T]":
        return Result(error=error)

    @property
    def ok(self) -> bool:
        return self._error is None

    @property
    def error(self) -> Optional[AppError]:
        return self._error

    def unwrap(self) -> T:
        """成功时返回值，失败时抛出错误"""
        if self._error is not None:
            raise self._error
        return self._value  # type: ignore[return-value]

    def unwrap_or(self, default: T) -> T:
        return default if self._error is not None else self._value  # type: ignore[return-value]

    def __repr__(self) -> str:
        state = "ok" if self.ok else f"error={self._error.code}"
        return f"Result({state})"
