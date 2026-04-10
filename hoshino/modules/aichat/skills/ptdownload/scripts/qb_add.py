#!/usr/bin/env python3
"""
qBittorrent 添加下载任务脚本
用法: python qb_add.py --url <下载链接> --category <分类>
"""
import sys
import json
import argparse
from typing import Dict, Any, Optional
from urllib.parse import urlparse

try:
    import aiohttp
    import asyncio
except ImportError as e:
    print(json.dumps({
        "success": False,
        "error": f"缺少依赖: {e}. 请安装: uv pip install aiohttp"
    }, ensure_ascii=False))
    sys.exit(1)

# 添加 skill 目录到路径
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from config import get_qb_config, get_stations, get_save_path, Config


class QBittorrentClient:
    """qBittorrent Web API 客户端"""
    
    def __init__(self, base_url: str, username: str, password: str, verify_ssl: bool = True):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self._cookie: Optional[str] = None
    
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
    
    async def add_torrent_file(
        self,
        session: aiohttp.ClientSession,
        torrent_data: bytes,
        save_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """通过种子文件数据添加下载任务"""
        
        if not self._cookie:
            if not await self.login(session):
                return {"success": False, "error": "登录失败，请检查用户名密码"}
        
        try:
            api_url = f"{self.base_url}/api/v2/torrents/add"
            
            data = aiohttp.FormData()
            data.add_field('torrents', torrent_data, filename='file.torrent', content_type='application/x-bittorrent')
            if save_path:
                data.add_field('savepath', save_path)
            data.add_field('autoTMM', 'false')
            
            headers = {"Cookie": self._cookie}
            
            async with session.post(api_url, headers=headers, data=data, ssl=self.verify_ssl) as resp:
                if resp.status in [200, 201]:
                    result_text = await resp.text()
                    if "Ok" in result_text or result_text.strip() == "":
                        return {"success": True}
                    else:
                        return {"success": False, "error": result_text}
                else:
                    return {"success": False, "error": f"HTTP {resp.status}"}
                    
        except Exception as e:
            return {"success": False, "error": str(e)}


def find_station_by_url(url: str) -> Optional[Dict[str, Any]]:
    """根据 URL 找到对应的 PT 站配置"""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    
    stations = get_stations()
    for station in stations:
        station_url = station.search_url
        if domain in station_url.lower():
            return station
    return None


async def download_torrent(url: str) -> Optional[bytes]:
    """使用对应 PT 站的 Cookie 下载种子文件"""
    station = find_station_by_url(url)
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    if station:
        headers.update(station.headers)
        print(f"使用 {station.name} 的 Cookie 下载种子", file=sys.stderr)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, ssl=False) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    if data.startswith(b'd8:') or data.startswith(b'd13:'):
                        return data
                    else:
                        text = data.decode('utf-8', errors='ignore')[:200]
                        print(f"下载内容不是种子文件: {text}", file=sys.stderr)
                        return None
                else:
                    print(f"下载失败: HTTP {resp.status}", file=sys.stderr)
                    return None
    except Exception as e:
        print(f"下载异常: {e}", file=sys.stderr)
        return None


async def add_by_url(url: str, title: str = "", category: str = "other") -> Dict[str, Any]:
    """根据 URL 添加下载"""
    
    config = get_qb_config()
    if not config.enabled:
        return {
            "success": False,
            "error": "qBittorrent 未启用，请在 config.json 中配置"
        }
    
    # 根据分类获取保存路径
    save_path = get_save_path(category)
    
    client = QBittorrentClient(
        base_url=config.base_url,
        username=config.username,
        password=config.password,
        verify_ssl=config.verify_ssl
    )
    
    is_magnet = url.startswith('magnet:')
    is_torrent_link = 'download.php' in url or url.endswith('.torrent')
    
    async with aiohttp.ClientSession() as session:
        if is_magnet:
            return {
                "success": False,
                "error": "磁力链接暂不支持，请使用 PT 站下载链接"
            }
        elif is_torrent_link:
            print(f"正在下载种子文件...", file=sys.stderr)
            torrent_data = await download_torrent(url)
            
            if torrent_data is None:
                return {
                    "success": False,
                    "error": "下载种子文件失败，可能是 Cookie 失效或链接无效"
                }
            
            print(f"种子文件大小: {len(torrent_data)} bytes", file=sys.stderr)
            print(f"保存路径: {save_path}", file=sys.stderr)
            
            result = await client.add_torrent_file(
                session=session,
                torrent_data=torrent_data,
                save_path=save_path
            )
        else:
            return {
                "success": False,
                "error": "不支持的链接格式，需要 PT 站下载链接"
            }
    
    if result.get('success'):
        return {
            "success": True,
            "message": "下载任务已添加",
            "title": title or url[:50] + "...",
            "category": category
        }
    else:
        return {
            "success": False,
            "error": result.get('error', '未知错误')
        }


def format_result(data: Dict[str, Any]) -> str:
    """格式化结果为可读文本"""
    
    if not data.get('success'):
        return f"❌ 添加失败: {data.get('error')}"
    
    title = data.get('title', '未知')
    category = data.get('category', 'other')
    
    # 分类名称映射
    cat_names = {
        'movie': '电影',
        'tv': '电视剧',
        'anime': '动漫',
        'r18': '成人向'
    }
    cat_name = cat_names.get(category, category)
    
    lines = [
        "✅ 已添加下载任务",
        "",
        f"📁 资源: {title}",
        f"🏷️ 分类: {cat_name}",
        "",
        "使用 qb_list.py 查看下载进度"
    ]
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='qBittorrent 添加下载')
    parser.add_argument('--url', required=True, help='PT 站下载链接')
    parser.add_argument('--title', default='', help='资源标题')
    parser.add_argument('--category', default='other',
                        choices=['movie', 'tv', 'anime', 'documentary', 'music', 'other'],
                        help='资源分类')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    
    args = parser.parse_args()
    
    result = asyncio.run(add_by_url(args.url, args.title, args.category))
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_result(result))
    
    sys.exit(0 if result.get('success') else 1)


if __name__ == "__main__":
    main()
