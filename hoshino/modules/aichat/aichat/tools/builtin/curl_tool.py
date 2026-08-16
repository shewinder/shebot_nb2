"""curl 工具 — 基于系统 curl 二进制的 HTTP 请求

设计动机（用户决策）：
- 不向 AI 暴露完整 shell（bash 限制的落地方式：AI 没有 shell 入口）
- 使用成熟的系统 curl，bot 不再维护自己的 HTTP 客户端逻辑
- 通过 create_subprocess_exec 参数数组执行（不经 shell），
  URL/头/请求体由 Pydantic 校验，杜绝命令注入
"""
import asyncio
import ipaddress
import json
import socket
from typing import Any, Dict, List, Literal, Optional, TYPE_CHECKING
from urllib.parse import urlparse

from loguru import logger
from pydantic import BaseModel, Field

from ..registry import tool_registry, ok, fail

if TYPE_CHECKING:
    from ...session import Session

MAX_OUTPUT = 50 * 1024      # 输出截断上限（与旧 fetch_url 一致）
MAX_TIME_DEFAULT = 30
MAX_TIME_CAP = 60
_PROCESS_TIMEOUT_MARGIN = 5


class CurlInput(BaseModel):
    """curl 工具输入模型"""

    url: str = Field(description="完整 URL（http/https）")
    method: Literal["GET", "POST"] = Field(default="GET", description="请求方法")
    headers: List[str] = Field(
        default_factory=list,
        description="请求头列表，如 ['Authorization: Bearer xxx', 'Content-Type: application/json']",
    )
    data: Optional[str] = Field(default=None, description="POST 请求体")
    max_time: int = Field(
        default=MAX_TIME_DEFAULT, ge=1, le=MAX_TIME_CAP,
        description=f"超时秒数（默认 {MAX_TIME_DEFAULT}，最大 {MAX_TIME_CAP}）",
    )


def _validate_url(url: str) -> tuple[bool, str]:
    """URL 校验：仅 http/https，且解析后的 IP 不能是私网/环回/保留地址（SSRF 防护）"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False, "仅支持 http/https URL"
    except ValueError:
        return False, "URL 解析失败"

    host = parsed.hostname
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False, f"域名解析失败: {host}"

    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        ):
            return False, f"拒绝访问内网/保留地址: {host} -> {ip}"
    return True, ""


def _validate_headers(headers: List[str]) -> tuple[bool, str]:
    """请求头校验：防 CRLF 注入"""
    for h in headers:
        if "\r" in h or "\n" in h:
            return False, "请求头包含非法换行符"
        if ":" not in h:
            return False, f"请求头格式非法（缺少冒号）: {h[:50]}"
    return True, ""


def _build_args(params: CurlInput) -> List[str]:
    args = ["curl", "-sS", "-L", "--max-time", str(params.max_time), "-X", params.method]
    for h in params.headers:
        args += ["-H", h]
    if params.data is not None:
        args += ["--data", params.data]
    args.append(params.url)
    return args


def _format_output(raw: str, content_type: str) -> str:
    """按 JSON/文本格式化并截断输出（沿用旧 fetch_url 的展示约定）"""
    is_json = "application/json" in content_type.lower() or raw.strip().startswith(("{", "["))
    if is_json:
        try:
            formatted = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            formatted = raw
        if len(formatted) > MAX_OUTPUT:
            formatted = formatted[:MAX_OUTPUT] + f"\n... (内容已截断，共 {len(formatted)} 字符)"
        return f"JSON 数据获取成功:\n```json\n{formatted}\n```"
    if len(raw) > MAX_OUTPUT:
        raw = raw[:MAX_OUTPUT] + f"\n... (内容已截断，共 {len(raw)} 字符)"
    return f"内容获取成功:\n```\n{raw}\n```"


@tool_registry.register(
    description="""使用系统 curl 发起 HTTP 请求（GET/POST），获取 JSON 或文本内容。

用于已知具体 URL 需要获取内容的场景，如 REST API 调用、网页抓取等。

使用优先级：
1. 当需要搜索信息但不确定具体链接时 → 使用 web_search
2. 当已知具体 URL 想获取内容时 → 使用 curl（本工具）

注意事项：
- 支持 GET/POST、自定义请求头、POST 请求体
- 仅允许公网 http/https 地址（内网地址会被拒绝）
- 返回内容超过 50KB 会被截断""",
)
async def curl(
    params: CurlInput,
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    ok_url, msg = _validate_url(params.url)
    if not ok_url:
        return fail(msg, error=msg)

    ok_headers, msg = _validate_headers(params.headers)
    if not ok_headers:
        return fail(msg, error=msg)

    args = _build_args(params)
    logger.info(f"[curl] {' '.join(a for a in args if not a.startswith('-H'))} headers={len(params.headers)}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return fail("系统未安装 curl，无法执行请求", error="curl not found")

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=params.max_time + _PROCESS_TIMEOUT_MARGIN,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return fail(f"curl 执行超时（>{params.max_time}s）", error="curl timeout")

    raw = stdout.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        err_text = stderr.decode("utf-8", errors="replace")[:200]
        logger.warning(f"[curl] 失败 rc={proc.returncode}: {err_text}")
        return fail(f"curl 请求失败: {err_text}", error=f"curl exit {proc.returncode}")

    # 从响应头推断 content-type（-i 未开启时取不到，退化为内容嗅探）
    content = _format_output(raw, "")
    return ok(
        content,
        metadata={"url": params.url, "method": params.method, "size": len(raw)},
    )
