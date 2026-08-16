"""全局指标统计（纯标准库，线程安全）

记录 LLM 调用与工具执行的延迟/token/错误码聚合数据。
跨事件循环与线程安全（threading.Lock），供日志汇总与命令展示。
"""
import threading
import time
from typing import Dict, Optional


class Metrics:
    """进程级指标聚合器"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.llm_calls = 0
        self.llm_error_codes: Dict[str, int] = {}
        self.llm_prompt_tokens = 0
        self.llm_completion_tokens = 0
        self.llm_latency_sum_ms = 0.0
        self.llm_latency_max_ms = 0.0
        self.tool_calls = 0
        self.tool_timeouts = 0
        self.tool_latency_sum_ms = 0.0

    def record_llm_call(
        self,
        latency_ms: float,
        usage: Optional[Dict[str, int]] = None,
    ) -> None:
        with self._lock:
            self.llm_calls += 1
            self.llm_latency_sum_ms += latency_ms
            self.llm_latency_max_ms = max(self.llm_latency_max_ms, latency_ms)
            if usage:
                self.llm_prompt_tokens += usage.get("prompt_tokens", 0) or 0
                self.llm_completion_tokens += usage.get("completion_tokens", 0) or 0

    def record_llm_error(self, code: str) -> None:
        with self._lock:
            self.llm_calls += 1
            self.llm_error_codes[code] = self.llm_error_codes.get(code, 0) + 1

    def record_tool_call(self, latency_ms: float) -> None:
        with self._lock:
            self.tool_calls += 1
            self.tool_latency_sum_ms += latency_ms

    def record_tool_timeout(self) -> None:
        with self._lock:
            self.tool_timeouts += 1

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            llm_avg = (self.llm_latency_sum_ms / self.llm_calls) if self.llm_calls else 0.0
            tool_avg = (self.tool_latency_sum_ms / self.tool_calls) if self.tool_calls else 0.0
            return {
                "started_at": self.started_at,
                "llm_calls": self.llm_calls,
                "llm_error_codes": dict(self.llm_error_codes),
                "llm_prompt_tokens": self.llm_prompt_tokens,
                "llm_completion_tokens": self.llm_completion_tokens,
                "llm_avg_latency_ms": llm_avg,
                "llm_max_latency_ms": self.llm_latency_max_ms,
                "tool_calls": self.tool_calls,
                "tool_timeouts": self.tool_timeouts,
                "tool_avg_latency_ms": tool_avg,
            }


metrics = Metrics()
