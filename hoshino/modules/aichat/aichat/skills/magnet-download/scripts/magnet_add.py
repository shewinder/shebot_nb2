#!/usr/bin/env python3
"""
添加磁力链接到 qBittorrent 下载
用法: python magnet_add.py --url <magnet链接> [--save-path <路径>] [--category <分类>]
      python magnet_add.py --list  # 查看下载进度
"""
import sys
import json
import argparse
from typing import Optional

try:
    import aiohttp
    import asyncio
except ImportError as e:
    print(json.dumps({
        "success": False,
        "error": f"缺少依赖: {e}. 请安装: uv pip install aiohttp"
    }, ensure_ascii=False))
    sys.exit(1)

sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from config import get_qb_config, get_save_path


class QBittorrentClient:
    """qBittorrent Web API 客户端（轻量版，仅用于磁力链接）"""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self._cookie: Optional[str] = None

    async def login(self, session: aiohttp.ClientSession) -> bool:
        try:
            url = f"{self.base_url}/api/v2/auth/login"
            async with session.post(url, data={
                "username": self.username,
                "password": self.password,
            }) as resp:
                if resp.status == 200:
                    cookies = resp.cookies
                    if cookies:
                        self._cookie = "; ".join(
                            f"{k}={v.value}" for k, v in cookies.items()
                        )
                        return True
                return False
        except Exception as e:
            print(f"登录失败: {e}", file=sys.stderr)
            return False

    async def _ensure_auth(self, session: aiohttp.ClientSession) -> bool:
        if self._cookie:
            return True
        return await self.login(session)

    async def add_magnet(
        self,
        session: aiohttp.ClientSession,
        magnet_url: str,
        save_path: Optional[str] = None,
        category: Optional[str] = None,
    ) -> dict:
        """通过磁力链接添加下载任务"""
        if not self._cookie and not await self.login(session):
            return {"success": False, "error": "qBittorrent 登录失败，请检查用户名密码"}

        try:
            api_url = f"{self.base_url}/api/v2/torrents/add"
            data = {"urls": magnet_url}
            if save_path:
                data["savepath"] = save_path
            if category:
                data["category"] = category
            data["autoTMM"] = "false"

            headers = {"Cookie": self._cookie}
            async with session.post(api_url, headers=headers, data=data) as resp:
                if resp.status in [200, 201]:
                    text = await resp.text()
                    if text.strip() == "" or "Ok" in text:
                        return {"success": True}
                    return {"success": False, "error": text}
                elif resp.status == 403:
                    self._cookie = None  # 会话过期，下次重新登录
                    return {"success": False, "error": "登录会话过期，请重试"}
                else:
                    return {"success": False, "error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_torrents(self, session: aiohttp.ClientSession) -> dict:
        """获取下载列表"""
        if not self._cookie and not await self.login(session):
            return {"success": False, "error": "qBittorrent 登录失败"}

        try:
            api_url = f"{self.base_url}/api/v2/torrents/info"
            headers = {"Cookie": self._cookie}
            async with session.get(api_url, headers=headers) as resp:
                if resp.status == 200:
                    torrents = await resp.json()
                    return {"success": True, "torrents": torrents}
                return {"success": False, "error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


def is_magnet_url(url: str) -> bool:
    return url.startswith("magnet:") or "magnet:?xt=" in url


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def format_speed(speed_bytes: int) -> str:
    """格式化速度"""
    if speed_bytes == 0:
        return "0 KB/s"
    for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
        if speed_bytes < 1024:
            return f"{speed_bytes:.1f} {unit}"
        speed_bytes /= 1024
    return f"{speed_bytes:.1f} GB/s"


def format_eta(eta_seconds: int) -> str:
    """格式化剩余时间"""
    if eta_seconds >= 8640000:  # qB 用这个值表示无限
        return "∞"
    if eta_seconds < 60:
        return f"{eta_seconds}秒"
    if eta_seconds < 3600:
        return f"{eta_seconds // 60}分钟"
    hours = eta_seconds // 3600
    minutes = (eta_seconds % 3600) // 60
    return f"{hours}小时{minutes}分钟"


STATE_NAMES = {
    "downloading": "下载中",
    "stalledDL": "等待中",
    "pausedDL": "已暂停",
    "queuedDL": "排队中",
    "checkingDL": "校验中",
    "uploading": "做种中",
    "stalledUP": "做种中",
    "pausedUP": "已暂停",
    "queuedUP": "排队中",
    "checkingUP": "校验中",
    "allocating": "分配空间",
    "metaDL": "获取元数据",
    "missingFiles": "文件缺失",
    "error": "错误",
    "unknown": "未知",
    "moving": "移动中",
}


async def cmd_add(args) -> dict:
    """添加磁力链接"""
    config = get_qb_config()
    if not config:
        return {
            "success": False,
            "error": "qBittorrent 未启用，请在 data/config/ptdownload.json 中配置 qbittorrent 连接信息"
        }

    client = QBittorrentClient(
        base_url=config["base_url"],
        username=config["username"],
        password=config["password"],
    )

    if args.save_path:
        save_path = args.save_path
    elif args.category:
        save_path = get_save_path(args.category)
    else:
        save_path = config.get("default_save_path")

    async with aiohttp.ClientSession() as session:
        result = await client.add_magnet(
            session=session,
            magnet_url=args.url,
            save_path=save_path,
            category=args.category,
        )

    if result.get("success"):
        result["magnet_hash"] = _extract_hash(args.url)
        result["save_path"] = save_path
    return result


async def cmd_list() -> dict:
    """查看下载列表"""
    config = get_qb_config()
    if not config:
        return {
            "success": False,
            "error": "qBittorrent 未启用"
        }

    client = QBittorrentClient(
        base_url=config["base_url"],
        username=config["username"],
        password=config["password"],
    )

    async with aiohttp.ClientSession() as session:
        result = await client.list_torrents(session)

    if result.get("success"):
        torrents = result["torrents"]
        if not torrents:
            result["summary"] = "📭 当前没有下载任务"
        else:
            lines = ["📊 下载列表", ""]
            for i, t in enumerate(torrents, 1):
                name = t.get("name", "未知")
                state = STATE_NAMES.get(t.get("state", ""), t.get("state", "未知"))
                progress = t.get("progress", 0) * 100
                size = format_size(t.get("size", 0))
                dlspeed = format_speed(t.get("dlspeed", 0))
                eta = format_eta(t.get("eta", 8640000))

                if progress >= 100:
                    line = f"{i}. ✅ {name} | {size} | {state}"
                else:
                    line = f"{i}. ⏳ {name} | {progress:.1f}% | {dlspeed} | 剩余 {eta} | {size}"
                lines.append(line)

            # 统计
            active = sum(1 for t in torrents if t.get("state") in ("downloading", "stalledDL"))
            lines.append("")
            lines.append(f"📈 活跃: {active} | 总数: {len(torrents)}")
            result["summary"] = "\n".join(lines)

    return result


def _extract_hash(magnet_url: str) -> str:
    """从磁力链接提取 info hash"""
    import re
    # 匹配 btih: 后面的 hash（可以是 hex 或 base32）
    match = re.search(r'btih:([0-9a-fA-F]{40})', magnet_url)
    if match:
        return match.group(1)[:16] + "..."
    match = re.search(r'btih:([0-9a-zA-Z]{32})', magnet_url)
    if match:
        return match.group(1)[:16] + "..."
    return "未知"


def format_result(data: dict) -> str:
    """格式化结果为可读文本"""
    if not data.get("success"):
        return f"❌ 操作失败: {data.get('error')}"

    # 列表结果
    if "summary" in data:
        return data["summary"]

    # 添加磁力结果
    lines = [
        "✅ 已添加下载任务",
        "",
        f"🔗 Hash: {data.get('magnet_hash', '未知')}",
        f"📁 保存路径: {data.get('save_path', '默认')}",
        "",
        "💡 发送「查看下载」可查看进度",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='磁力链接下载（qBittorrent）')
    parser.add_argument('--url', help='磁力链接 (magnet:?xt=...)')
    parser.add_argument('--save-path', help='保存路径（覆盖默认）')
    parser.add_argument('--category', help='分类标签')
    parser.add_argument('--list', action='store_true', help='查看下载进度')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')

    args = parser.parse_args()

    if args.list:
        result = asyncio.run(cmd_list())
    elif args.url:
        result = asyncio.run(cmd_add(args))
    else:
        parser.print_help()
        sys.exit(1)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_result(result))

    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
