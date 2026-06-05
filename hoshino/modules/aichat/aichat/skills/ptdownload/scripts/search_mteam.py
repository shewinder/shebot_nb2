#!/usr/bin/env python3
"""
M-Team 搜索 & 下载脚本

用法:
  python search_mteam.py <关键词> [--mode normal|free] [--json]       # 搜索
  python search_mteam.py --add <下载链接> --title <标题>                # 下载种子 + 添加到 qBittorrent
"""
import argparse
import asyncio
import base64
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx

API_BASE = "https://api.m-team.cc"
SEARCH_ENDPOINT = "/api/torrent/search"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"

# 分类名称映射
CATEGORY_NAMES: Dict[str, str] = {
    "401": "电影", "402": "电视剧", "403": "综艺",
    "404": "纪录片", "405": "动画", "406": "MV",
    "407": "体育", "408": "音乐", "409": "游戏",
    "410": "学习", "411": "软件",
}


def _parse_date(date_str: str) -> Optional[datetime]:
    """解析 M-Team 时间格式: '2026-05-31 16:32:36'"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _is_free(torrent: dict) -> bool:
    """判断种子是否实际免费（含商城单人免费）"""
    discount = torrent.get("discount") or torrent.get("status", {}).get("discount", "")
    if discount in ("FREE", "PERCENT_100"):
        return True
    mf = torrent.get("mall_free") or torrent.get("status", {}).get("mallSingleFree")
    if mf and mf.get("status") == "ONGOING":
        return True
    return False


def _format_size(size_bytes) -> str:
    """字节数转可读格式"""
    size_bytes = int(size_bytes) if size_bytes else 0
    gb = size_bytes / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.2f} GB"
    mb = size_bytes / (1024 ** 2)
    return f"{mb:.0f} MB"


async def search(
    keyword: str,
    free_only: bool = False,
    page: int = 1,
    size: int = 100,
) -> Dict[str, Any]:
    """搜索 M-Team，默认同时搜 adult + normal"""
    auth = os.environ.get("PT_MSTEAM_AUTH", "")
    if not auth:
        return {"success": False, "error": "M-Team API Token 未配置，请设置 PT_MSTEAM_AUTH 环境变量"}

    api_modes = ["adult", "normal"]

    headers = {
        "x-api-key": auth,
        "content-type": "application/json",
        "accept": "application/json",
        "user-agent": USER_AGENT,
    }

    all_torrents: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for api_mode in api_modes:
                body: Dict[str, Any] = {
                    "keyword": keyword,
                    "mode": api_mode,
                    "visible": 1,
                    "categories": [],
                    "pageNumber": page,
                    "pageSize": size,
                }
                resp = await client.post(
                    urljoin(API_BASE, SEARCH_ENDPOINT),
                    json=body,
                    headers=headers,
                )
                data = resp.json()
                if data.get("code") != "0":
                    return {"success": False, "error": data.get("message", "未知错误")}
                all_torrents.extend(data["data"]["data"])
    except Exception as e:
        return {"success": False, "error": f"API 请求失败: {e}"}

    # 去重（同一个 id 可能出现在多个 mode 中）
    seen: set[str] = set()
    torrents: list[dict] = []
    for t in all_torrents:
        tid = t["id"]
        if tid not in seen:
            seen.add(tid)
            torrents.append(t)

    if free_only:
        torrents = [t for t in torrents if _is_free(t)]

    results = []
    for t in torrents:
        status = t.get("status", {})
        results.append({
            "id": t["id"],
            "title": t["name"],
            "description": t.get("smallDescr", ""),
            "size": _format_size(t.get("size", 0)),
            "size_bytes": int(t.get("size", 0)),
            "seeders": int(status.get("seeders", 0)),
            "leechers": int(status.get("leechers", 0)),
            "download": f"https://kp.m-team.cc/download.php?id={t['id']}",
            "category": CATEGORY_NAMES.get(str(t.get("category", "")), str(t.get("category", ""))),
            "created_date": t.get("createdDate", ""),
            "discount": status.get("discount", ""),
            "discount_end": status.get("discountEndTime", ""),
            "mall_free": status.get("mallSingleFree"),
            "douban_rating": t.get("doubanRating"),
            "station": "M-Team",
        })

    return {
        "success": True,
        "keyword": keyword,
        "free_only": free_only,
        "count": len(results),
        "results": results,
    }


def format_results(data: Dict[str, Any]) -> str:
    if not data.get("success"):
        return f"❌ 搜索失败: {data.get('error')}"

    results = data.get("results", [])
    if not results:
        return f"🔍 M-Team 未找到「{data.get('keyword')}」相关资源"

    lines = [f"🔍 M-Team 搜索到 {data.get('count')} 个资源：\n"]
    for i, r in enumerate(results, 1):
        discount = r.get("discount", "")
        free_label = " 🆓免费" if _is_free(r) else ""
        labels = [l for l in [f"[{discount}]" if discount and discount != "NORMAL" else "", free_label] if l]
        label_str = "".join(labels)
        lines.append(f"{i}. [{r['station']}] {r['title'][:50]}{label_str}")
        lines.append(f"   大小: {r['size']} | 做种: {r['seeders']} | 下载: {r['leechers']} | 分类: {r.get('category', '-')}")
        if r.get("discount_end"):
            lines.append(f"   折扣截止: {r['discount_end']}")
        if r.get("mall_free"):
            mf = r["mall_free"]
            lines.append(f"   商城免费: {mf['startDate']} ~ {mf['endDate']} ({mf['freeDay']}天)")
        lines.append(f"   下载链接: {r['download']}")
        lines.append("")

    lines.append('\n💡 回复"下载第N个"选择下载')
    return "\n".join(lines)


async def download_torrent(download_url_or_id: str) -> Optional[bytes]:
    """下载 M-Team 的 .torrent 文件（通过 API，无需 Cookie）

    支持两种输入：
    - 下载链接 (https://kp.m-team.cc/download.php?id=xxx)
    - 种子 ID (纯数字)
    """
    auth = os.environ.get("PT_MSTEAM_AUTH", "")
    if not auth:
        print("⚠ PT_MSTEAM_AUTH 未配置", file=sys.stderr)
        return None

    # 从 URL 或直接输入中提取种子 ID
    import re
    tid_match = re.search(r'id[=/](\d+)', download_url_or_id) or re.match(r'^(\d+)$', download_url_or_id.strip())
    if not tid_match:
        print(f"无法从输入中提取种子 ID: {download_url_or_id}", file=sys.stderr)
        return None
    tid = tid_match.group(1)

    headers = {
        "x-api-key": auth,
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": USER_AGENT,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # 1. 获取签名下载链接
            resp = await client.post(
                urljoin(API_BASE, "/api/torrent/genDlToken"),
                content=f"id={tid}",
                headers=headers,
            )
            data = resp.json()
            if data.get("code") != "0":
                print(f"获取下载链接失败: {data.get('message')}", file=sys.stderr)
                return None

            # 2. 下载种子文件
            dl_url = data["data"]
            dl_headers = {"x-api-key": auth, "user-agent": USER_AGENT}
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as dl_client:
                resp2 = await dl_client.get(dl_url, headers=dl_headers)
                if resp2.status_code != 200:
                    print(f"下载失败: HTTP {resp2.status_code}", file=sys.stderr)
                    return None
                content = resp2.content
                if content[:3] == b"d8:" or content[:3] == b"d13":
                    print(f"种子下载成功: {len(content)} bytes", file=sys.stderr)
                    return content
                print(f"不是有效的种子文件", file=sys.stderr)
                return None
    except Exception as e:
        print(f"下载异常: {e}", file=sys.stderr)
        return None


async def add_and_download(ids: list[str], category: str = "") -> Dict[str, Any]:
    """批量下载种子并提交到 qBittorrent"""
    from qb_add import add as qb_add

    success = 0
    failed = 0
    for tid in ids:
        torrent_data = await download_torrent(tid)
        if not torrent_data:
            failed += 1
            continue
        result = await qb_add(torrent_data, category)
        if result["success"]:
            success += 1
        else:
            failed += 1
    return {"success": failed == 0, "count": len(ids), "ok": success, "failed": failed}


def main():
    parser = argparse.ArgumentParser(description="M-Team 搜索与下载")
    parser.add_argument("keyword", nargs="?", default="", help="搜索关键词（可留空）")
    parser.add_argument("--free", action="store_true", help="仅免费种")
    parser.add_argument("--add", nargs="*", help="下载种子并添加到 qBittorrent（传入种子 ID，可多个）")
    parser.add_argument("--category", default="", help="qb 分类（如 电影/动漫/R18）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    args = parser.parse_args()

    if args.add:
        result = asyncio.run(add_and_download(args.add, args.category))
    else:
        result = asyncio.run(search(args.keyword, free_only=args.free))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.add:
        label = f" [{args.category}]" if args.category else ""
        print(f"✅ {result.get('ok', 0)}/{result.get('count', 0)} 已添加{label}" if result["success"] else f"❌ {result.get('ok', 0)}/{result.get('count', 0)} 成功{label}")
    else:
        print(format_results(result))

    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
