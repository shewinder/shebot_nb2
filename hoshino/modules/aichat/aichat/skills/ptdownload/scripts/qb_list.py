#!/usr/bin/env python3
"""
qBittorrent 任务列表查看脚本
用法: python qb_list.py [--json]
"""
import os
import sys
import json
import argparse
from typing import Dict, Any, List

try:
    import aiohttp
    import asyncio
except ImportError as e:
    print(json.dumps({
        "success": False,
        "error": f"缺少依赖: {e}. 请安装: uv pip install aiohttp"
    }, ensure_ascii=False))
    sys.exit(1)


class QBittorrentClient:
    """qBittorrent Web API 客户端"""
    
    def __init__(self, base_url: str, username: str, password: str, verify_ssl: bool = True):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self._cookie: str = ""
    
    async def login(self, session: aiohttp.ClientSession) -> bool:
        """登录获取 Session"""
        try:
            url = f"{self.base_url}/api/v2/auth/login"
            data = {
                "username": self.username,
                "password": self.password
            }
            async with session.post(url, data=data, ssl=self.verify_ssl) as resp:
                if resp.status == 200:
                    cookies = resp.cookies
                    if cookies:
                        self._cookie = "; ".join([f"{k}={v.value}" for k, v in cookies.items()])
                        return True
                return False
        except Exception as e:
            print(f"登录失败: {e}", file=sys.stderr)
            return False
    
    async def get_torrents(self, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """获取任务列表"""
        
        if not self._cookie:
            if not await self.login(session):
                return {"success": False, "error": "登录失败"}
        
        try:
            url = f"{self.base_url}/api/v2/torrents/info"
            headers = {"Cookie": self._cookie}
            
            async with session.get(url, headers=headers, ssl=self.verify_ssl) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"success": True, "data": data}
                else:
                    return {"success": False, "error": f"HTTP {resp.status}"}
                    
        except Exception as e:
            return {"success": False, "error": str(e)}


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes/1024:.1f}KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes/1024**2:.1f}MB"
    else:
        return f"{size_bytes/1024**3:.2f}GB"


def format_speed(speed_bytes: int) -> str:
    """格式化速度"""
    if speed_bytes == 0:
        return "0 B/s"
    if speed_bytes < 1024 ** 2:
        return f"{speed_bytes/1024:.1f}KB/s"
    else:
        return f"{speed_bytes/1024**2:.2f}MB/s"


def format_progress(progress: float) -> str:
    """格式化进度"""
    return f"{progress * 100:.1f}%"


def state_icon(state: str) -> str:
    """状态图标"""
    icons = {
        'downloading': '⬇️',
        'stalledDL': '⏳',
        'uploading': '⬆️',
        'stalledUP': '✅',
        'pausedDL': '⏸️',
        'pausedUP': '✅',
        'queuedDL': '⏳',
        'queuedUP': '⏳',
        'checkingDL': '🔍',
        'checkingUP': '🔍',
        'error': '❌',
        'missingFiles': '⚠️',
        'forcedDL': '⬇️',
        'forcedUP': '⬆️',
    }
    return icons.get(state, '❓')


def state_text(state: str) -> str:
    """状态文字"""
    texts = {
        'downloading': '下载中',
        'stalledDL': '等待中',
        'uploading': '做种中',
        'stalledUP': '做种中',
        'pausedDL': '已暂停',
        'pausedUP': '已完成',
        'queuedDL': '队列中',
        'queuedUP': '队列中',
        'checkingDL': '校验中',
        'checkingUP': '校验中',
        'error': '错误',
        'missingFiles': '文件缺失',
        'forcedDL': '强制下载',
        'forcedUP': '强制上传',
    }
    return texts.get(state, state)


def format_torrents(data: List[Dict[str, Any]], search: str = "") -> str:
    """格式化任务列表"""

    if not data:
        return "📭 当前没有下载任务"

    # 按名称过滤
    if search:
        data = [t for t in data if search.lower() in t.get('name', '').lower()]
        if not data:
            return f"📭 未找到包含「{search}」的任务"

    total = len(data)
    lines = [f"📥 qBittorrent 任务列表（共 {total} 个{f', 筛选: {search}' if search else ''}）\n"]

    # 按状态排序：下载中 -> 队列中 -> 做种中 -> 其他
    def sort_key(t):
        priority = {
            'downloading': 0, 'forcedDL': 0,
            'stalledDL': 1, 'queuedDL': 2, 'checkingDL': 3,
            'uploading': 4, 'forcedUP': 4, 'stalledUP': 5,
        }
        return priority.get(t.get('state', ''), 10)

    sorted_torrents = sorted(data, key=sort_key)

    for i, t in enumerate(sorted_torrents, 1):
        name = t.get('name', '未知')[:40]
        state = t.get('state', 'unknown')
        progress = t.get('progress', 0)
        size = format_size(t.get('total_size', 0))
        downloaded = format_size(t.get('completed', 0))
        dlspeed = format_speed(t.get('dlspeed', 0))
        upspeed = format_speed(t.get('upspeed', 0))

        icon = state_icon(state)
        status = state_text(state)

        lines.append(f"{i}. {icon} {name}")
        lines.append(f"   状态: {status} | 进度: {format_progress(progress)} | 大小: {size}")

        if state in ['downloading', 'forcedDL', 'stalledDL']:
            lines.append(f"   下载: {downloaded} | 速度: {dlspeed}")
        elif state in ['uploading', 'forcedUP', 'stalledUP']:
            lines.append(f"   上传速度: {upspeed}")

        lines.append("")

    return "\n".join(lines)


async def list_torrents() -> Dict[str, Any]:
    """获取并格式化任务列表"""

    base_url = os.environ.get("PT_QB_URL", "http://localhost:8080")
    username = os.environ.get("PT_QB_USERNAME", "admin")
    password = os.environ.get("PT_QB_PASSWORD", "")

    client = QBittorrentClient(
        base_url=base_url,
        username=username,
        password=password,
        verify_ssl=False,
    )
    
    async with aiohttp.ClientSession() as session:
        result = await client.get_torrents(session)
    
    if result.get('success'):
        return {
            "success": True,
            "count": len(result.get('data', [])),
            "torrents": result.get('data', [])
        }
    else:
        return result


def main():
    parser = argparse.ArgumentParser(description='qBittorrent 任务列表')
    parser.add_argument('--search', help='按名称过滤（子串匹配）')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')

    args = parser.parse_args()

    result = asyncio.run(list_torrents())

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result.get('success'):
        print(format_torrents(result.get('torrents', []), search=args.search or ""))
    else:
        print(f"❌ 获取失败: {result.get('error')}")
    
    sys.exit(0 if result.get('success') else 1)


if __name__ == "__main__":
    main()
