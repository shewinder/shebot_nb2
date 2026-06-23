#!/usr/bin/env python3
"""
qBittorrent 添加下载任务

用法:
  python qb_add.py --file <种子文件> --category <分类>
  python qb_add.py --data <base64种子数据> --category <分类>

分类: 电影 / 动漫 / R18 等（qb 内置分类系统，自动存到对应目录）
"""
import argparse
import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

import aiohttp


class QBittorrentClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._cookie: Optional[str] = None

    async def login(self, session: aiohttp.ClientSession) -> bool:
        try:
            url = f"{self.base_url}/api/v2/auth/login"
            async with session.post(url, data={"username": self.username, "password": self.password}) as resp:
                if resp.status == 200:
                    raw = resp.headers.get("Set-Cookie", "")
                    self._cookie = raw.split(";")[0] if raw else ""
                    if not self._cookie:
                        print(f"qBittorrent 登录失败: Set-Cookie 为空", file=sys.stderr)
                    return bool(self._cookie)
                print(f"qBittorrent 登录失败: HTTP {resp.status}", file=sys.stderr)
                return False
        except Exception as e:
            print(f"qBittorrent 登录失败: {e}", file=sys.stderr)
            return False

    async def add_torrent(self, session: aiohttp.ClientSession, torrent_data: bytes, category: str = "", save_path: str = "") -> Dict[str, Any]:
        if not self._cookie and not await self.login(session):
            return {"success": False, "error": "qBittorrent 登录失败"}

        data = aiohttp.FormData()
        data.add_field("torrents", torrent_data, filename="file.torrent", content_type="application/x-bittorrent")
        if category:
            data.add_field("category", category)
        if save_path:
            data.add_field("savepath", save_path)
        data.add_field("autoTMM", "false")

        headers = {"Cookie": self._cookie}
        async with session.post(f"{self.base_url}/api/v2/torrents/add", headers=headers, data=data) as resp:
            text = await resp.text()
            if resp.status in (200, 201) and (text.strip() == "" or "Ok" in text):
                return {"success": True}
            error_msg = text.strip() or f"HTTP {resp.status}"
            print(f"qBittorrent 添加失败: {error_msg}", file=sys.stderr)
            return {"success": False, "error": error_msg}


async def add(torrent_data: bytes, category: str = "") -> Dict[str, Any]:
    base_url = os.environ.get("PT_QB_URL", "http://localhost:8080")
    username = os.environ.get("PT_QB_USERNAME", "admin")
    password = os.environ.get("PT_QB_PASSWORD", "")

    client = QBittorrentClient(base_url, username, password)
    async with aiohttp.ClientSession() as session:
        # 查询分类获取对应路径
        save_path = ""
        cats = await list_categories()
        if cats.get("success"):
            cat_info = cats["categories"].get(category, {})
            save_path = cat_info.get("savePath", "")
        return await client.add_torrent(session, torrent_data, category, save_path)


async def list_categories() -> Dict[str, Any]:
    """获取 qb 分类列表"""
    base_url = os.environ.get("PT_QB_URL", "http://localhost:8080")
    username = os.environ.get("PT_QB_USERNAME", "admin")
    password = os.environ.get("PT_QB_PASSWORD", "")
    async with aiohttp.ClientSession() as session:
        client = QBittorrentClient(base_url, username, password)
        if not await client.login(session):
            return {"success": False, "error": "qBittorrent 登录失败"}
        headers = {"Cookie": client._cookie}
        async with session.get(f"{base_url}/api/v2/torrents/categories", headers=headers) as resp:
            return {"success": True, "categories": await resp.json()}


def main():
    parser = argparse.ArgumentParser(description="qBittorrent 添加下载")
    parser.add_argument("--file", help="种子文件路径")
    parser.add_argument("--data", help="base64 编码的种子数据")
    parser.add_argument("--category", default="", help="qb 分类")
    parser.add_argument("--list-categories", action="store_true", help="获取可用分类")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.list_categories:
        result = asyncio.run(list_categories())
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif result["success"]:
            for name, info in result["categories"].items():
                path = info.get("savePath", "")
                print(f"  {name}: {path}" if path else f"  {name}")
        else:
            print(f"❌ {result.get('error')}")
        sys.exit(0 if result["success"] else 1)

    if args.file:
        torrent_data = Path(args.file).read_bytes()
    elif args.data:
        torrent_data = base64.b64decode(args.data)
    else:
        print(json.dumps({"success": False, "error": "需要 --file 或 --data"}))
        sys.exit(1)

    result = asyncio.run(add(torrent_data, args.category))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        label = f" [{args.category}]" if args.category else ""
        print(f"✅ 已添加{label}" if result["success"] else f"❌ 失败: {result.get('error')}")
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
