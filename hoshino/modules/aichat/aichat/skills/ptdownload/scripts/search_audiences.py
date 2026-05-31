#!/usr/bin/env python3
"""
audiences 搜索脚本 — HTML 抓取

用法: python search_audiences.py <关键词> [--json]
"""
import argparse
import asyncio
import json
import os
import sys
from typing import Optional
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

SEARCH_URL = "https://audiences.me/torrents.php?search={keyword}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


async def search(keyword: str) -> dict:
    """搜索 audiences"""
    cookie = os.environ.get("PT_AUDIENCES_COOKIE", "")
    if not cookie:
        return {"success": False, "error": "audiences Cookie 未配置"}

    headers = {
        "User-Agent": USER_AGENT,
        "Cookie": cookie,
        "Accept": "text/html,application/xhtml+xml",
    }

    try:
        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            resp = await client.get(
                SEARCH_URL.format(keyword=quote(keyword)),
                headers=headers,
            )
            html = resp.text
    except Exception as e:
        return {"success": False, "error": f"请求失败: {e}"}

    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.torrents tr")
    results = []
    for row in rows:
        try:
            title_el = row.select_one("a[href*='details.php']")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            dl_el = row.select_one("a[href*='download.php']")
            download = urljoin(SEARCH_URL, dl_el["href"]) if dl_el else ""
            size_el = row.select_one("td:nth-child(5)")
            size = size_el.get_text(strip=True) if size_el else "-"
            seeders_el = row.select_one("td:nth-child(6)")
            seeders = seeders_el.get_text(strip=True) if seeders_el else "0"

            results.append({
                "title": title,
                "download": download,
                "size": size,
                "seeders": seeders,
                "station": "audiences",
            })
        except Exception:
            continue

    return {"success": True, "keyword": keyword, "count": len(results), "results": results}


def format_results(data: dict) -> str:
    if not data.get("success"):
        return f"❌ 搜索失败: {data.get('error')}"

    results = data.get("results", [])
    if not results:
        return f"🔍 audiences 未找到「{data.get('keyword')}」相关资源"

    lines = [f"🔍 audiences 搜索到 {len(results)} 个资源：\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. [{r['station']}] {r['title'][:50]}")
        lines.append(f"   大小: {r['size']} | 做种: {r['seeders']}")
        if r.get("download"):
            lines.append(f"   下载链接: {r['download']}")
        lines.append("")

    lines.append('\n💡 回复"下载第N个"选择下载')
    return "\n".join(lines)


async def download_torrent(url: str) -> Optional[bytes]:
    """下载 audiences 的 .torrent 文件"""
    cookie = os.environ.get("PT_AUDIENCES_COOKIE", "")
    if not cookie:
        print("⚠ PT_AUDIENCES_COOKIE 未配置", file=sys.stderr)
        return None

    headers = {"User-Agent": USER_AGENT, "Cookie": cookie}
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                print(f"下载失败: HTTP {resp.status_code}", file=sys.stderr)
                return None
            data = resp.content
            if data.startswith(b"d8:") or data.startswith(b"d13:"):
                return data
            print(f"不是有效的种子文件", file=sys.stderr)
            return None
    except Exception as e:
        print(f"下载异常: {e}", file=sys.stderr)
        return None


async def add_from_url(url: str, category: str = "") -> dict:
    torrent_data = await download_torrent(url)
    if not torrent_data:
        return {"success": False, "error": "下载种子文件失败"}
    from qb_add import add as qb_add
    return await qb_add(torrent_data, category)


def main():
    parser = argparse.ArgumentParser(description="audiences 搜索与下载")
    parser.add_argument("keyword", nargs="?", help="搜索关键词")
    parser.add_argument("--add", help="下载种子并添加到 qBittorrent（传入下载链接）")
    parser.add_argument("--category", default="", help="qb 分类（如 电影/动漫/R18）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.add:
        result = asyncio.run(add_from_url(args.add, args.category))
    elif args.keyword:
        result = asyncio.run(search(args.keyword))
    else:
        parser.error("需要搜索关键词 或 --add <下载链接>")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.add:
        print(f"✅ 已添加: {result.get('title', '')}" if result["success"] else f"❌ 失败: {result.get('error', '')}")
    else:
        print(format_results(result))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
