#!/usr/bin/env python3
"""
qBittorrent Web API 管理脚本。
"""
import argparse
import asyncio
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx


DEFAULT_SAVE_PATH = "/downloads"
INFINITE_ETA = 8640000

STATE_NAMES: Dict[str, str] = {
    "downloading": "下载中",
    "stalledDL": "等待中",
    "pausedDL": "已暂停",
    "queuedDL": "排队中",
    "checkingDL": "校验中",
    "forcedDL": "强制下载",
    "uploading": "做种中",
    "stalledUP": "做种中",
    "pausedUP": "已完成",
    "queuedUP": "排队中",
    "checkingUP": "校验中",
    "forcedUP": "强制做种",
    "allocating": "分配空间",
    "metaDL": "获取元数据",
    "missingFiles": "文件缺失",
    "error": "错误",
    "moving": "移动中",
    "unknown": "未知",
}

STATE_ICONS: Dict[str, str] = {
    "downloading": "⬇️",
    "stalledDL": "⏳",
    "pausedDL": "⏸️",
    "queuedDL": "⏳",
    "checkingDL": "🔍",
    "forcedDL": "⬇️",
    "uploading": "⬆️",
    "stalledUP": "✅",
    "pausedUP": "✅",
    "queuedUP": "⏳",
    "checkingUP": "🔍",
    "forcedUP": "⬆️",
    "allocating": "📦",
    "metaDL": "🔎",
    "missingFiles": "⚠️",
    "error": "❌",
    "moving": "📁",
}


@dataclass
class QBConfig:
    base_url: str
    username: str
    password: str
    default_save_path: str
    verify_ssl: bool


def parse_bool(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def get_config() -> Optional[QBConfig]:
    base_url = os.environ.get("PT_QB_URL", "").strip()
    if not base_url:
        return None
    return QBConfig(
        base_url=base_url.rstrip("/"),
        username=os.environ.get("PT_QB_USERNAME", "admin"),
        password=os.environ.get("PT_QB_PASSWORD", ""),
        default_save_path=os.environ.get("PT_QB_SAVE_PATH", DEFAULT_SAVE_PATH),
        verify_ssl=parse_bool(os.environ.get("PT_QB_VERIFY_SSL", ""), default=False),
    )


def fail(error: str, **extra: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {"success": False, "error": error}
    result.update(extra)
    return result


def ok(**extra: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {"success": True}
    result.update(extra)
    return result


def format_size(size_bytes: int) -> str:
    value = float(size_bytes or 0)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def format_speed(speed_bytes: int) -> str:
    value = float(speed_bytes or 0)
    for unit in ["B/s", "KB/s", "MB/s", "GB/s"]:
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB/s"


def format_eta(eta_seconds: int) -> str:
    if eta_seconds >= INFINITE_ETA:
        return "∞"
    if eta_seconds < 60:
        return f"{eta_seconds}秒"
    if eta_seconds < 3600:
        return f"{eta_seconds // 60}分钟"
    hours = eta_seconds // 3600
    minutes = (eta_seconds % 3600) // 60
    return f"{hours}小时{minutes}分钟"


def parse_hash_values(values: Optional[List[List[str]]]) -> List[str]:
    if not values:
        return []
    hashes: List[str] = []
    for group in values:
        for value in group:
            for part in re.split(r"[,\|\s]+", value.strip()):
                if part:
                    hashes.append(part)
    return hashes


def combine_hashes(values: Optional[List[List[str]]]) -> str:
    hashes = parse_hash_values(values)
    return "|".join(hashes)


def join_hashes(hashes: List[str]) -> str:
    return "|".join(hashes)


def unique_values(values: List[str]) -> List[str]:
    seen: set[str] = set()
    unique: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


class QBittorrentClient:
    """qBittorrent Web API 客户端。"""

    def __init__(self, config: QBConfig):
        self.config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=30,
            verify=config.verify_ssl,
            follow_redirects=True,
        )
        self._logged_in = False

    async def __aenter__(self) -> "QBittorrentClient":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def login(self) -> Dict[str, Any]:
        if self._logged_in:
            return ok()
        try:
            resp = await self._client.post(
                "/api/v2/auth/login",
                data={"username": self.config.username, "password": self.config.password},
            )
        except Exception as e:
            return fail(f"qBittorrent 登录失败: {e}")
        text = resp.text.strip()
        if resp.status_code == 200 and (text == "" or text.lower().startswith("ok")):
            self._logged_in = True
            return ok()
        return fail(f"qBittorrent 登录失败: {text or f'HTTP {resp.status_code}'}")

    async def _ensure_auth(self) -> Dict[str, Any]:
        return await self.login()

    async def _post_action(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        auth = await self._ensure_auth()
        if not auth.get("success"):
            return auth
        try:
            resp = await self._client.post(endpoint, data=data)
        except Exception as e:
            return fail(str(e))
        text = resp.text.strip()
        if resp.status_code in (200, 201) and (text == "" or text.lower().startswith("ok")):
            return ok()
        return fail(text or f"HTTP {resp.status_code}")

    async def categories(self) -> Dict[str, Any]:
        auth = await self._ensure_auth()
        if not auth.get("success"):
            return auth
        try:
            resp = await self._client.get("/api/v2/torrents/categories")
        except Exception as e:
            return fail(str(e))
        if resp.status_code != 200:
            return fail(f"HTTP {resp.status_code}")
        return ok(categories=resp.json())

    async def list_torrents(
        self,
        filter_name: str = "",
        category: str = "",
        hashes: str = "",
    ) -> Dict[str, Any]:
        auth = await self._ensure_auth()
        if not auth.get("success"):
            return auth

        params: Dict[str, str] = {}
        if filter_name and filter_name != "all":
            params["filter"] = filter_name
        if category:
            params["category"] = category
        if hashes:
            params["hashes"] = hashes

        try:
            resp = await self._client.get("/api/v2/torrents/info", params=params)
        except Exception as e:
            return fail(str(e))
        if resp.status_code != 200:
            return fail(f"HTTP {resp.status_code}")
        torrents = resp.json()
        return ok(count=len(torrents), torrents=torrents)

    async def pause(self, hashes: str) -> Dict[str, Any]:
        return await self._post_action("/api/v2/torrents/pause", {"hashes": hashes})

    async def resume(self, hashes: str) -> Dict[str, Any]:
        return await self._post_action("/api/v2/torrents/resume", {"hashes": hashes})

    async def delete(self, hashes: str, delete_files: bool) -> Dict[str, Any]:
        return await self._post_action(
            "/api/v2/torrents/delete",
            {"hashes": hashes, "deleteFiles": "true" if delete_files else "false"},
        )

    async def recheck(self, hashes: str) -> Dict[str, Any]:
        return await self._post_action("/api/v2/torrents/recheck", {"hashes": hashes})

    async def set_category(self, hashes: str, category: str) -> Dict[str, Any]:
        return await self._post_action(
            "/api/v2/torrents/setCategory",
            {"hashes": hashes, "category": category},
        )


async def with_client() -> Dict[str, Any]:
    config = get_config()
    if config is None:
        return fail("qBittorrent 未配置，请设置 PT_QB_URL 等环境变量")
    return ok(config=config)


async def list_categories() -> Dict[str, Any]:
    setup = await with_client()
    if not setup.get("success"):
        return setup
    async with QBittorrentClient(setup["config"]) as client:
        return await client.categories()


async def list_torrents(
    filter_name: str = "",
    category: str = "",
    hashes: str = "",
    search: str = "",
) -> Dict[str, Any]:
    setup = await with_client()
    if not setup.get("success"):
        return setup
    async with QBittorrentClient(setup["config"]) as client:
        result = await client.list_torrents(filter_name, category, hashes)
    if result.get("success") and search:
        result["total_count"] = result.get("count", 0)
        result["search"] = search
        result["torrents"] = filter_torrents(result.get("torrents", []), search)
        result["count"] = len(result["torrents"])
    return result


async def list_torrents_by_hash_values(hash_values: List[str]) -> Dict[str, Any]:
    setup = await with_client()
    if not setup.get("success"):
        return setup
    async with QBittorrentClient(setup["config"]) as client:
        resolved = await resolve_hashes(client, hash_values)
        if not resolved.get("success"):
            return resolved
        return await client.list_torrents(hashes=resolved["hashes"])


async def resolve_hashes(client: QBittorrentClient, hash_values: List[str]) -> Dict[str, Any]:
    if not hash_values:
        return fail("缺少任务 hash")

    list_result = await client.list_torrents()
    if not list_result.get("success"):
        return fail(f"获取任务列表失败: {list_result.get('error', '未知错误')}")

    torrents = list_result.get("torrents", [])
    torrent_hashes = [str(torrent.get("hash", "")).lower() for torrent in torrents if torrent.get("hash")]
    resolved: List[str] = []
    missing: List[str] = []
    ambiguous: Dict[str, List[str]] = {}

    for raw_hash in hash_values:
        query = raw_hash.lower()
        matches = [torrent_hash for torrent_hash in torrent_hashes if torrent_hash.startswith(query)]
        if len(matches) == 1:
            resolved.append(matches[0])
        elif len(matches) == 0:
            missing.append(raw_hash)
        else:
            ambiguous[raw_hash] = matches[:10]

    if missing or ambiguous:
        details: List[str] = []
        if missing:
            details.append(f"未找到: {', '.join(missing)}")
        if ambiguous:
            conflicts = [f"{key} -> {', '.join(values)}" for key, values in ambiguous.items()]
            details.append(f"匹配多个: {'; '.join(conflicts)}")
        return fail("hash 解析失败，未执行操作。" + "；".join(details))

    resolved = unique_values(resolved)
    return ok(hashes=join_hashes(resolved), count=len(resolved))


async def run_resolved_action(
    action: str,
    hash_values: List[str],
    category: str = "",
    delete_files: bool = False,
) -> Dict[str, Any]:
    setup = await with_client()
    if not setup.get("success"):
        return setup

    async with QBittorrentClient(setup["config"]) as client:
        resolved = await resolve_hashes(client, hash_values)
        if not resolved.get("success"):
            return resolved
        hashes = resolved["hashes"]
        if action == "pause":
            result = await client.pause(hashes)
        elif action == "resume":
            result = await client.resume(hashes)
        elif action == "delete":
            result = await client.delete(hashes, delete_files)
            if result.get("success"):
                check_result = await client.list_torrents(hashes=hashes)
                if not check_result.get("success"):
                    return fail(
                        f"删除请求已发送，但复查失败: {check_result.get('error', '未知错误')}",
                        hashes=hashes,
                    )
                remaining = check_result.get("torrents", []) if check_result.get("success") else []
                if remaining:
                    return fail(
                        "qBittorrent 返回成功，但任务仍存在",
                        hashes=hashes,
                        remaining_count=len(remaining),
                    )
        elif action == "recheck":
            result = await client.recheck(hashes)
        elif action == "set-category":
            result = await client.set_category(hashes, category)
        else:
            return fail(f"未知操作: {action}")

    if result.get("success"):
        result.update({"action": action, "hashes": hashes, "count": resolved.get("count", 0)})
        if category:
            result["category"] = category
        if action == "delete":
            result["delete_files"] = delete_files
    return result


def format_categories(result: Dict[str, Any]) -> str:
    if not result.get("success"):
        return f"❌ 获取分类失败: {result.get('error')}"
    categories = result.get("categories", {})
    if not categories:
        return "📁 当前没有 qb 分类"
    lines = ["📁 qBittorrent 分类"]
    for name, info in categories.items():
        path = info.get("savePath", "")
        lines.append(f"- {name}: {path}" if path else f"- {name}")
    return "\n".join(lines)


def filter_torrents(torrents: List[Dict[str, Any]], search: str) -> List[Dict[str, Any]]:
    keyword = search.strip().lower()
    if not keyword:
        return torrents
    matched: List[Dict[str, Any]] = []
    for torrent in torrents:
        fields = [
            torrent.get("name", ""),
            torrent.get("hash", ""),
            torrent.get("category", ""),
            torrent.get("save_path", ""),
        ]
        if any(keyword in str(field).lower() for field in fields):
            matched.append(torrent)
    return matched


def short_hash(torrent_hash: str) -> str:
    if not torrent_hash:
        return "nohash"
    return torrent_hash[:12]


def format_hashes_for_display(hashes: str) -> str:
    values = [value for value in hashes.split("|") if value]
    if not values:
        return ""
    shown = ", ".join(short_hash(value) for value in values[:20])
    if len(values) > 20:
        shown = f"{shown}, ... 等{len(values)}个"
    return shown


def format_torrents(torrents: List[Dict[str, Any]]) -> str:
    if not torrents:
        return "📭 当前没有下载任务"

    def sort_key(torrent: Dict[str, Any]) -> int:
        priority = {
            "downloading": 0,
            "forcedDL": 0,
            "stalledDL": 1,
            "metaDL": 2,
            "queuedDL": 3,
            "checkingDL": 4,
            "uploading": 5,
            "forcedUP": 5,
            "stalledUP": 6,
            "pausedUP": 7,
            "pausedDL": 8,
        }
        return priority.get(torrent.get("state", ""), 20)

    sorted_torrents = sorted(torrents, key=sort_key)
    lines = [f"📥 qBittorrent 任务列表（共 {len(sorted_torrents)} 个）", ""]
    for index, torrent in enumerate(sorted_torrents, 1):
        name = torrent.get("name", "未知")
        torrent_hash = short_hash(str(torrent.get("hash", "")))
        state = torrent.get("state", "unknown")
        icon = STATE_ICONS.get(state, "❓")
        status = STATE_NAMES.get(state, state)
        progress = float(torrent.get("progress", 0)) * 100
        size = format_size(torrent.get("total_size") or torrent.get("size") or 0)
        path = torrent.get("save_path", "") or ""
        parts = [f"{icon} {status} {progress:.1f}%", size]

        if state in ("downloading", "forcedDL", "stalledDL", "metaDL"):
            parts.append(f"↓{format_speed(torrent.get('dlspeed', 0))}")
            parts.append(f"剩余 {format_eta(torrent.get('eta', INFINITE_ETA))}")
        elif state in ("uploading", "forcedUP", "stalledUP"):
            upspeed = torrent.get("upspeed", 0)
            if upspeed:
                parts.append(f"↑{format_speed(upspeed)}")
        if path:
            parts.append(path)
        lines.append(f"{index}. [{torrent_hash}] {name} | {' | '.join(parts)}")
    return "\n".join(lines)


def format_action_result(result: Dict[str, Any]) -> str:
    if not result.get("success"):
        return f"❌ 操作失败: {result.get('error')}"
    names = {
        "pause": "已暂停",
        "resume": "已恢复",
        "delete": "已删除",
        "recheck": "已提交重校验",
        "set-category": "已修改分类",
    }
    action = result.get("action", "")
    text = names.get(action, "操作成功")
    count = result.get("count", 0)
    hashes = format_hashes_for_display(result.get("hashes", ""))
    count_text = f"{count} 个任务" if count and count > 1 else "任务"
    return f"✅ {text} {count_text}: {hashes}"


def format_result(command: str, result: Dict[str, Any]) -> str:
    if command == "categories":
        return format_categories(result)
    if command in ("list", "status"):
        if not result.get("success"):
            return f"❌ 获取失败: {result.get('error')}"
        return format_torrents(result.get("torrents", []))
    return format_action_result(result)


async def run_command(args: argparse.Namespace) -> Dict[str, Any]:
    if args.command == "categories":
        return await list_categories()
    if args.command == "list":
        hashes = combine_hashes(args.hashes)
        return await list_torrents(args.filter, args.category, hashes, args.search)
    if args.command == "status":
        return await list_torrents_by_hash_values(parse_hash_values(args.hashes))
    if args.command == "delete" and not args.confirm:
        return fail("删除任务需要先获得用户明确确认，并传入 --confirm")
    if args.command in ("pause", "resume", "delete", "recheck", "set-category"):
        return await run_resolved_action(
            action=args.command,
            hash_values=parse_hash_values(args.hashes),
            category=getattr(args, "category", ""),
            delete_files=getattr(args, "delete_files", False),
        )
    return fail(f"未知命令: {args.command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="qBittorrent 管理")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("categories", help="获取 qb 分类")

    list_parser = subparsers.add_parser("list", help="查看下载任务")
    list_parser.add_argument("--filter", default="", help="qb 过滤器，如 downloading/completed/active")
    list_parser.add_argument("--category", default="", help="qb 分类")
    list_parser.add_argument("--search", default="", help="按名称、hash、分类或保存路径筛选任务")
    list_parser.add_argument("--hash", dest="hashes", action="append", nargs="+", help="任务 hash，可传多个，也可重复传")

    status = subparsers.add_parser("status", help="查看指定任务")
    status.add_argument("--hash", dest="hashes", action="append", nargs="+", required=True, help="任务 hash，可传多个，也可重复传")

    for command in ("pause", "resume", "recheck"):
        action_parser = subparsers.add_parser(command, help=f"{command} 任务")
        action_parser.add_argument("--hash", dest="hashes", action="append", nargs="+", required=True, help="任务 hash，可传多个，也可重复传")

    delete = subparsers.add_parser("delete", help="删除任务")
    delete.add_argument("--hash", dest="hashes", action="append", nargs="+", required=True, help="任务 hash，可传多个，也可重复传")
    delete.add_argument("--delete-files", action="store_true", help="同时删除本地文件")
    delete.add_argument("--confirm", action="store_true", help="确认删除")

    set_category = subparsers.add_parser("set-category", help="修改任务分类")
    set_category.add_argument("--hash", dest="hashes", action="append", nargs="+", required=True, help="任务 hash，可传多个，也可重复传")
    set_category.add_argument("--category", required=True, help="目标分类")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = asyncio.run(run_command(args))
    print(format_result(args.command, result))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
