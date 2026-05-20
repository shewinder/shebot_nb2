#!/usr/bin/env python3
"""
Vision 筛选独立测试 —— 零依赖 bot 框架，直接测试核心逻辑

用法:
    cd /root/bot/shebot_nb2
    .venv/bin/python hoshino/modules/pixiv/pixivrank/test_vision_standalone.py
    .venv/bin/python hoshino/modules/pixiv/pixivrank/test_vision_standalone.py -n 10 -b 5 -u 2
    .venv/bin/python hoshino/modules/pixiv/pixivrank/test_vision_standalone.py --multi-group

数据: data/pixiv/pixiv_rank_r18.json
API:  data/config/aichat.json → 云雾中转
"""
import argparse
import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp
import httpx

# ── 配置路径 ──────────────────────────────────────────
PROJECT = Path(__file__).resolve().parent.parent.parent.parent.parent
RANK_FILE = PROJECT / "data" / "pixiv" / "pixiv_rank_r18.json"
AICHAT_CONF = PROJECT / "data" / "config" / "aichat.json"
PREF_DIR = PROJECT / "data" / "aichat" / "preferences"
CACHE_DIR = PROJECT / "data" / "pixiv" / "vision_cache"

# ── 全局配置（模拟 conf.xxx） ────────────────────────
class _Config:
    vision_api_base = ""
    vision_api_key = ""
    vision_model = "gemini-3.1-flash-lite"
    vision_batch_size = 10
    vision_select_per_user = 4

conf = _Config()
_image_cache: Dict[int, str] = {}  # 内存缓存（同一次运行内复用）


# ── 核心函数（从 vision_filter.py 提取，logger → print） ──

def _disk_cache_path(pid: int) -> Path:
    return CACHE_DIR / f"{pid}.b64.txt"


def _load_from_disk(pid: int) -> Optional[str]:
    p = _disk_cache_path(pid)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None


def _save_to_disk(pid: int, b64: str):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _disk_cache_path(pid).write_text(b64, encoding="utf-8")


async def _download_image(image_url: str) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    return None
                image_data = await resp.read()
                if not image_data:
                    return None
                content_type = resp.content_type or ""
                ext = "png"
                if content_type.startswith("image/"):
                    ext = content_type.split("/")[1].split(";")[0].strip()
                    if ext == "jpeg":
                        ext = "jpg"
                else:
                    if "." in image_url:
                        url_part = image_url.split("?")[0]
                        url_ext = os.path.splitext(url_part)[1].lower()
                        if url_ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                            ext = url_ext.lstrip(".")
                return f"data:image/{ext};base64,{base64.b64encode(image_data).decode('utf-8')}"
    except Exception:
        return None


async def _download_image_cached(pid: int, url: str) -> Optional[str]:
    # 1. 内存缓存
    if pid in _image_cache:
        return _image_cache[pid]
    # 2. 磁盘缓存
    b64 = _load_from_disk(pid)
    if b64:
        _image_cache[pid] = b64
        return b64
    # 3. 网络下载
    b64 = await _download_image(url)
    if b64:
        _image_cache[pid] = b64
        _save_to_disk(pid, b64)
    return b64


def _extract_profile_summary(pref: str) -> str:
    in_section = False
    for line in pref.split("\n"):
        line = line.strip()
        if "核心审美画像" in line or "核心偏好摘要" in line:
            in_section = True
            continue
        if in_section and line.startswith("##"):
            break
        if in_section and len(line) > 20 and not line.startswith(">"):
            return line[:120]
    lines = [l.strip() for l in pref.split("\n") if len(l.strip()) > 30]
    return lines[0][:120] if lines else ""


async def _call_vision_batch(
    batch_images: List[Tuple[int, str]],
    user_preferences: List[Tuple[str, bool, str]],
    select_per_user: int,
) -> Optional[Dict[int, List[int]]]:
    user_texts = []
    for i, (pref, is_su, uid) in enumerate(user_preferences):
        if not pref:
            continue
        summary = _extract_profile_summary(pref)
        su_tag = "【超级用户】" if is_su else ""
        user_texts.append(f"【用户{i}】{su_tag} ID:{uid}\n偏好摘要:{summary}\n完整画像:{pref[:800]}")

    users_block = "\n\n".join(user_texts)
    pid_labels = [f"PID:{pid}" for pid, _ in batch_images]

    content_parts = [
        {
            "type": "text",
            "text": (
                f"候选图片标签: {', '.join(pid_labels)}\n\n"
                f"【用户画像】\n{users_block}\n\n"
                f"以下是 {len(batch_images)} 张候选图片，每张图上方有 PID 标签："
            )
        }
    ]
    for pid, b64_url in batch_images:
        content_parts.append({"type": "text", "text": f"\n--- PID:{pid} ---"})
        content_parts.append({"type": "image_url", "image_url": {"url": b64_url}})

    system_prompt = (
        f"你是图片推荐助手。根据每位用户的审美偏好，从候选图片中为每人选 {select_per_user} 张最符合的。\n"
        "看构图、色调、风格、主题，匹配画像中的审美偏好。返回 JSON，不要解释：\n"
        '{"user_0": [pid1, pid2, ...], "user_1": [...], ...}'
    )

    api_base = conf.vision_api_base.rstrip("/")
    print(f"    POST {api_base}/chat/completions")
    print(f"    Model: {conf.vision_model}, 图片: {len(batch_images)}张, 用户: {len(user_preferences)}人")

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {conf.vision_api_key}", "Content-Type": "application/json"},
            json={
                "model": conf.vision_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content_parts},
                ],
                "temperature": 0.3,
                "max_tokens": 1000,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        print(f"    Token: {json.dumps(data.get('usage', {}))}")
        print(f"    Model: {data.get('model', '?')}")
        print(f"    Finish: {data['choices'][0].get('finish_reason', '?')}")
        print(f"    --- API 返回 ---")
        print(f"    {content}")
        print(f"    --- 结束 ---")

    json_str = content.strip()
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0]
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0]
    result = json.loads(json_str.strip())

    user_selections: Dict[int, List[int]] = {}
    valid_pids = {pid for pid, _ in batch_images}
    for i in range(len(user_preferences)):
        key = f"user_{i}"
        if key in result:
            pids = []
            for pid in result[key]:
                try:
                    pid_int = int(pid)
                    if pid_int in valid_pids:
                        pids.append(pid_int)
                except (ValueError, TypeError):
                    pass
            if pids:
                user_selections[i] = pids[:select_per_user]
    return user_selections


async def vision_filter_images(
    images: List[Dict],
    user_preferences: List[Tuple[str, bool, str]],
) -> Tuple[Optional[List[int]], Dict[int, List[Tuple[int, bool]]]]:
    if not user_preferences or not conf.vision_api_key:
        return None, {}

    user_count = len(user_preferences)
    batch_size = conf.vision_batch_size
    select_per_user = conf.vision_select_per_user

    print(f"Vision 筛选: {user_count}用户, {len(images)}张图, 每批{batch_size}张, 每人选{select_per_user}张")

    # 分片
    batches = [images[i:i + batch_size] for i in range(0, len(images), batch_size)]
    print(f"分 {len(batches)} 批，开始并行下载...")

    async def download_batch(batch: List[Dict]) -> List[Tuple[int, str]]:
        async def download_one(img: Dict):
            url = img.get("url", "")
            if not url:
                url = f"https://pixiv.shewinder.win/img/{img['pid']}"
            else:
                url = url.replace("i.pximg.net", "pixiv.shewinder.win")
            b64 = await _download_image_cached(img["pid"], url)
            if b64:
                return (img["pid"], b64)
            print(f"    ⚠ 下载失败 PID:{img['pid']}")
            return None
        results = await asyncio.gather(*[download_one(img) for img in batch])
        return [r for r in results if r is not None]

    downloaded_batches = await asyncio.gather(*[download_batch(b) for b in batches])
    total_downloaded = sum(len(b) for b in downloaded_batches)
    print(f"下载完成: {total_downloaded}/{len(images)} 张, 缓存命中: {len(_image_cache) - total_downloaded}")

    # 并行调用 API
    print(f"开始 {len(batches)} 批并行 API 调用...")
    async def call_batch(batch_images):
        if not batch_images:
            return None
        try:
            return await _call_vision_batch(batch_images, user_preferences, select_per_user)
        except httpx.HTTPStatusError as e:
            print(f"    ✗ HTTP {e.response.status_code}: {e.response.text[:200]}")
            return None
        except json.JSONDecodeError as e:
            print(f"    ✗ JSON解析失败: {e}")
            return None
        except Exception as e:
            print(f"    ✗ API调用失败: {e}")
            return None

    batch_results = await asyncio.gather(*[call_batch(b) for b in downloaded_batches])

    vote_details: Dict[int, List[Tuple[int, bool]]] = {}
    for result in batch_results:
        if result:
            for user_idx, pids in result.items():
                is_su = user_preferences[user_idx][1] if user_idx < len(user_preferences) else False
                for pid in pids:
                    vote_details.setdefault(pid, []).append((user_idx, is_su))

    if not vote_details:
        print("所有批均未返回有效结果")
        return None, {}

    def sort_key(pid):
        details = vote_details[pid]
        count = len(details)
        has_su = any(is_su for _, is_su in details)
        first_su_idx = min((idx for idx, is_su in details if is_su), default=999)
        return (count, has_su, -first_su_idx)

    sorted_pids = sorted(vote_details.keys(), key=sort_key, reverse=True)
    print(f"汇总: {len(vote_details)} 张作品入选\n")
    return sorted_pids, vote_details


async def vision_filter_multi_group(
    images, group_preferences, target_count=15
) -> Dict[int, List[int]]:
    if not group_preferences:
        return {}

    flat_users = []
    user_group_map = {}
    idx = 0
    for gid, prefs in group_preferences.items():
        for pref, is_su, uid in prefs:
            if not pref:
                continue
            flat_users.append((pref, is_su, uid))
            user_group_map[idx] = gid
            idx += 1

    if not flat_users:
        return {}

    print(f"跨群合并: {len(group_preferences)}群, {len(flat_users)}用户, {len(images)}张图")
    sorted_pids, vote_details = await vision_filter_images(images, flat_users)
    if not sorted_pids:
        return {}

    group_votes = {gid: {} for gid in group_preferences}
    for pid, voters in vote_details.items():
        for user_idx, is_su in voters:
            gid = user_group_map.get(user_idx)
            if gid is not None:
                group_votes[gid].setdefault(pid, []).append((user_idx, is_su))

    def sort_key(pid, details):
        count = len(details)
        has_su = any(is_su for _, is_su in details)
        first_su_idx = min((idx for idx, is_su in details if is_su), default=999)
        return (count, has_su, -first_su_idx)

    results = {}
    for gid, votes in group_votes.items():
        if not votes:
            results[gid] = []
            continue
        g_sorted = sorted(votes.keys(), key=lambda pid: sort_key(pid, votes[pid]), reverse=True)
        results[gid] = g_sorted[:target_count]
        print(f"  群{gid}: {len(g_sorted)}张 → 取前{target_count}张")
    return results


# ── 测试流程 ──────────────────────────────────────────

def load_config():
    """从 aichat.json 加载中转站 API 并写入 conf"""
    data = json.loads(AICHAT_CONF.read_text())
    for api in data.get("apis", []):
        if "中转" in api.get("api", ""):
            conf.vision_api_base = api["api_base"]
            conf.vision_api_key = api["api_key"]
            print(f"API : {api['api']} | {conf.vision_api_base}")
            print(f"Model: {conf.vision_model}")
            return
    raise RuntimeError("未找到中转站 API 配置")


def load_images(limit: int) -> List[Dict]:
    data = json.loads(RANK_FILE.read_text())
    images = []
    for item in data.get("raw", [])[:limit]:
        images.append({
            "pid": item["pid"],
            "title": item.get("title", ""),
            "author": item.get("author", ""),
            "tags": item.get("tags", []),
            "url": item.get("url", "").replace("i.pximg.net", "pixiv.shewinder.win"),
        })
    print(f"数据: {len(images)} 张 (日期: {data.get('date')})\n")
    return images


def load_preferences(count: int) -> List[Tuple[str, bool, str]]:
    result = []
    if PREF_DIR.exists():
        for f in list(PREF_DIR.glob("*.md"))[:count]:
            content = f.read_text(encoding="utf-8").strip()
            if content:
                is_su = (len(result) == 0)
                result.append((content, is_su, f.stem))
    while len(result) < count:
        i = len(result)
        sample = (
            "# 核心审美画像\n"
            f"测试用户{i}: 偏好冷色调、几何构图、光影对比强烈的作品。"
            f"偏好科幻/赛博朋克/未来主义主题。回避甜腻幼化风格。\n"
            f"## 详细偏好\n"
            f"- 色调: 冷色系，蓝紫黑\n"
            f"- 构图: 大面积留白，几何线条\n"
            f"- 主题: 科幻、赛博朋克、机械\n"
            f"- 风格: 写实、半写实、厚涂\n"
        )
        result.append((sample, len(result) == 0, f"test_{i}"))
    return result


async def main():
    ap = argparse.ArgumentParser(description="Vision 筛选独立测试")
    ap.add_argument("-n", "--images", type=int, default=20, help="图片数量 (默认20)")
    ap.add_argument("-b", "--batch", type=int, default=10, help="每批数量 (默认10)")
    ap.add_argument("-u", "--users", type=int, default=3, help="用户数 (默认3)")
    ap.add_argument("--multi-group", action="store_true", help="测试跨群合并")
    ap.add_argument("--dry-run", action="store_true", help="仅下载图片不调API")
    ap.add_argument("--clear-cache", action="store_true", help="清除磁盘缓存后重新下载")
    args = ap.parse_args()

    print("=" * 60)
    print("Vision 筛选独立测试")
    print("=" * 60)

    load_config()
    images = load_images(args.images)
    conf.vision_batch_size = args.batch
    user_prefs = load_preferences(args.users)

    print(f"测试参数: 图片={len(images)}张, 每批={args.batch}张, 用户={len(user_prefs)}人")
    for pref, is_su, uid in user_prefs:
        summary = _extract_profile_summary(pref)
        su = " [SU]" if is_su else ""
        print(f"  {uid}{su}: {summary[:80]}...")
    print()

    if args.clear_cache:
        import shutil
        if CACHE_DIR.exists():
            shutil.rmtree(CACHE_DIR)
            print(f"已清除磁盘缓存: {CACHE_DIR}\n")
        else:
            print("磁盘缓存为空\n")

    # 磁盘缓存统计
    disk_cached = len(list(CACHE_DIR.glob("*.txt"))) if CACHE_DIR.exists() else 0
    print(f"磁盘缓存: {disk_cached} 张\n")

    if args.dry_run:
        print("--- Dry Run: 仅下载图片 ---")
        _image_cache.clear()
        tasks = [_download_image_cached(img["pid"], img["url"].replace("i.pximg.net", "pixiv.shewinder.win"))
                 for img in images]
        results = await asyncio.gather(*tasks)
        ok = sum(1 for r in results if r)
        new_disk = len(list(CACHE_DIR.glob("*.txt"))) - disk_cached if CACHE_DIR.exists() else 0
        print(f"结果: {ok}/{len(images)} 张 (新缓存 {max(0, new_disk)} 张)\n")
        return

    # 单群测试
    _image_cache.clear()
    print("--- 单群 Vision 筛选 ---")
    selected, votes = await vision_filter_images(images, user_prefs)

    print(f"结果: {len(selected)} 张入选\n")
    for pid in selected[:10]:
        voters = votes.get(pid, [])
        info = [f"u{v[0]}" + ("[SU]" if v[1] else "") for v in voters]
        img = next((i for i in images if i["pid"] == pid), None)
        title = img["title"][:40] if img else "?"
        print(f"  PID:{pid:>10}  [{len(voters)}票]  {title}")
        print(f"               ← {', '.join(info)}")

    # 跨群合并
    if args.multi_group:
        print(f"\n--- 跨群合并 (2个群) ---")
        _image_cache.clear()
        group_prefs = {10001: user_prefs[:2], 10002: user_prefs[2:]}
        group_pids = await vision_filter_multi_group(images, group_prefs)
        for gid, pids in group_pids.items():
            print(f"  群{gid}: {len(pids)} 张  {pids[:5]}...")

    print(f"\n{'=' * 60}")
    print("测试完成")


if __name__ == "__main__":
    asyncio.run(main())
