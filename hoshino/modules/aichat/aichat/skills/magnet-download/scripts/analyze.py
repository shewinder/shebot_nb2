#!/usr/bin/env python3
"""
磁力链接验车 → whatslink.info API，直接下载截图到 ImageStore

用法:
  python analyze.py <磁链或hash> [--json]
"""
import argparse
import asyncio
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import httpx

API_BASE = "https://whatslink.info"
API_PATH = "/api/v1/link"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://whatslink.info/",
}
MAX_RETRIES = 10
RETRY_DELAY = 2

# ---- ImageStoreCore 动态加载 ----
_project_root = Path(os.environ.get("PROJECT_ROOT", "."))
_core_path = _project_root / "hoshino" / "modules" / "aichat" / "aichat" / "_image_store_core.py"
if _core_path.exists():
    spec = importlib.util.spec_from_file_location("image_store_core", str(_core_path))
    _mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_mod)
    ImageStoreCore = _mod.ImageStoreCore
else:
    ImageStoreCore = None


def store_screenshot(image_bytes: bytes) -> Optional[dict]:
    """将截图存入 Session ImageStore，返回 {identifier, path}"""
    if ImageStoreCore is None:
        return None
    try:
        session_id = os.environ.get("SESSION_ID", "unknown")
        store = ImageStoreCore(session_id)
        entry = store.store_bytes(image_bytes, "ai", "jpg")
        return {
            "identifier": entry.identifier,
            "path": str(entry.file_path),
        }
    except Exception:
        return None


def parse_magnet(text: str) -> Optional[str]:
    """从磁链或纯 hash 中提取 infohash"""
    m = re.search(r"magnet:\?xt=urn:btih:(\w+)", text, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    m = re.match(r"^([0-9a-fA-F]{32,40})$", text.strip())
    if m:
        return m.group(1).lower()
    return None


def hum_size(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = 1024.0
    for u in units:
        if value / size < 1:
            return f"{value:.2f} {u}"
        value /= size
    return f"{value:.2f} PB"


async def analyze(infohash: str) -> dict:
    """调 whatslink.info 获取种子信息"""
    magnet_url = f"magnet:?xt=urn:btih:{infohash}"
    url = f"{API_BASE}{API_PATH}?url={magnet_url}"

    last_error = ""
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=HEADERS)
                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code}"
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                data = resp.json()
                err = data.get("error", "")
                if err:
                    if "quota" in err.lower():
                        print(f"频率限制，第{attempt+1}次重试...", file=sys.stderr)
                        await asyncio.sleep(RETRY_DELAY)
                        continue
                    return {"success": False, "error": err, "infohash": infohash}
                if data.get("type", "").strip() == "UNKNOWN":
                    return {"success": False, "error": "未找到种子信息", "infohash": infohash}

                # 下载并存储截图
                screenshots = []
                screenshot_urls = [s["screenshot"] for s in data.get("screenshots", [])[:5]]
                for img_url in screenshot_urls:
                    try:
                        async with httpx.AsyncClient(timeout=15) as img_client:
                            img_resp = await img_client.get(img_url, headers=HEADERS)
                            if img_resp.status_code == 200:
                                stored = store_screenshot(img_resp.content)
                                if stored:
                                    screenshots.append(stored)
                    except Exception as e:
                        print(f"下载截图失败 {img_url}: {e}", file=sys.stderr)

                return {
                    "success": True,
                    "infohash": infohash,
                    "name": data.get("name", ""),
                    "size": data.get("size", 0),
                    "size_human": hum_size(data.get("size", 0)),
                    "count": data.get("count", 0),
                    "type": data.get("type", ""),
                    "file_type": data.get("file_type", ""),
                    "screenshots": screenshots,
                    "screenshot_urls": screenshot_urls,
                }
        except Exception as e:
            last_error = str(e)
            await asyncio.sleep(RETRY_DELAY)

    return {"success": False, "error": f"重试{MAX_RETRIES}次后仍失败: {last_error}", "infohash": infohash}


def format_result(data: dict) -> str:
    """人类可读输出"""
    if not data.get("success"):
        return f"❌ 验车失败: {data.get('error')}"

    lines = [
        f"🔍 验车结果",
        f"种子名称: {data['name']}",
        f"文件类型: {data['type']}-{data['file_type']}",
        f"总大小: {data['size_human']}",
        f"文件数: {data['count']}",
        f"Hash: {data['infohash']}",
    ]
    screenshots = data.get("screenshots", [])
    if screenshots:
        identifiers = " ".join(s["identifier"] for s in screenshots)
        lines.append(f"\n📸 截图: {identifiers}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="磁力链接验车")
    parser.add_argument("link", help="磁力链接或种子 hash")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    infohash = parse_magnet(args.link)
    if not infohash:
        result = {"success": False, "error": "无法解析磁力链接或 hash"}
    else:
        result = asyncio.run(analyze(infohash))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_result(result))

    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
