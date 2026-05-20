'''
Author: SheBot
Date: 2026-05-20
Description: Vision 视觉筛选 — 分批调用 vision 模型看图筛选图片
'''
import asyncio
import base64
import json
import os
from typing import Dict, List, Optional, Tuple

import aiohttp
import httpx
from hoshino.log import logger

from .config import Config

conf = Config.get_instance("pixivrank")

# 图片下载缓存：pid -> base64 data URL，跨群共享
_image_cache: Dict[int, str] = {}


async def _download_image(image_url: str) -> Optional[str]:
    """下载图片并转为 base64 data URL"""
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
                base64_data = base64.b64encode(image_data).decode("utf-8")
                return f"data:image/{ext};base64,{base64_data}"
    except Exception:
        return None


async def _download_image_cached(pid: int, url: str) -> Optional[str]:
    """下载图片并缓存，按 PID 跨群复用"""
    if pid in _image_cache:
        return _image_cache[pid]
    b64 = await _download_image(url)
    if b64:
        _image_cache[pid] = b64
    return b64


def _extract_profile_summary(pref: str) -> str:
    """从画像提取核心审美摘要首句"""
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
    batch_images: List[Tuple[int, str]],  # [(pid, b64_data_url), ...]
    user_preferences: List[Tuple[str, bool, str]],  # [(pref_text, is_superuser, user_id), ...]
    select_per_user: int,
) -> Optional[Dict[int, List[int]]]:
    """单批 vision 调用，返回 {user_idx: [pid, ...]}"""

    # 构造用户画像文本
    user_texts = []
    for i, (pref, is_su, uid) in enumerate(user_preferences):
        if not pref:
            continue
        summary = _extract_profile_summary(pref)
        su_tag = "【超级用户】" if is_su else ""
        user_texts.append(
            f"【用户{i}】{su_tag} ID:{uid}\n偏好摘要:{summary}\n完整画像:{pref[:800]}"
        )

    users_block = "\n\n".join(user_texts)

    # 构造图片标签列表
    pid_labels = [f"PID:{pid}" for pid, _ in batch_images]

    # 构造 content_parts: 文本说明 + 每张图的标签和图片
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
        content_parts.append({
            "type": "text",
            "text": f"\n--- PID:{pid} ---"
        })
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": b64_url}
        })

    system_prompt = f"""你是图片推荐助手。根据每位用户的审美偏好，从候选图片中为每人选 {select_per_user} 张最符合的。

看构图、色调、风格、主题，匹配画像中的审美偏好。返回 JSON，不要解释：
{{"user_0": [pid1, pid2, ...], "user_1": [...], ...}}"""

    api_base = conf.vision_api_base.rstrip("/")
    api_key = conf.vision_api_key
    model = conf.vision_model

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content_parts}
                ],
                "temperature": 0.3,
                "max_tokens": 1000
            }
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]

        # 解析 JSON
        json_str = content.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        result = json.loads(json_str.strip())

        # 构建返回: {user_idx: [pid, ...]}
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
    """
    分批调用 vision 模型筛选图片

    Args:
        images: 候选图片列表 [{"pid", "title", "author", "tags"}, ...]
        user_preferences: [(preference_text, is_superuser, user_id), ...]

    Returns:
        (排序后的 PID 列表, 投票明细 {pid: [(user_idx, is_superuser), ...]})
    """
    if not user_preferences or not conf.vision_api_key:
        return None, {}

    user_count = len(user_preferences)
    batch_size = conf.vision_batch_size
    select_per_user = conf.vision_select_per_user

    logger.info(
        f"Vision 筛选开始: 用户={user_count}人, 候选={len(images)}张, "
        f"每批={batch_size}张, 每人选={select_per_user}张"
    )

    # 分片
    batches = []
    for i in range(0, len(images), batch_size):
        batches.append(images[i:i + batch_size])

    logger.info(f"分 {len(batches)} 批，开始并行下载和筛选")

    # 每批并行下载图片（使用缓存）
    async def download_batch(batch: List[Dict]) -> List[Tuple[int, str]]:
        """下载一批图片，返回 [(pid, b64_url), ...]"""
        async def download_one(img: Dict):
            url = img.get("url", "")
            if not url:
                url = f"https://pixiv.shewinder.win/img/{img['pid']}"
            else:
                url = url.replace("i.pximg.net", "pixiv.shewinder.win")
            b64 = await _download_image_cached(img["pid"], url)
            if b64:
                return (img["pid"], b64)
            else:
                logger.warning(f"Vision 筛选: 图片下载失败 PID:{img['pid']}")
                return None

        tasks = [download_one(img) for img in batch]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]

    downloaded_batches = await asyncio.gather(*[download_batch(b) for b in batches])

    # 每批并行调用 vision API
    async def call_batch(batch_images: List[Tuple[int, str]]) -> Optional[Dict[int, List[int]]]:
        if len(batch_images) == 0:
            return None
        try:
            return await _call_vision_batch(batch_images, user_preferences, select_per_user)
        except httpx.HTTPStatusError as e:
            logger.error(f"Vision API HTTP 错误: {e.response.status_code} - {e.response.text[:200]}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Vision API JSON 解析失败: {e}")
            return None
        except Exception as e:
            logger.exception(f"Vision API 调用失败: {e}")
            return None

    batch_results = await asyncio.gather(*[call_batch(b) for b in downloaded_batches])

    # 汇总投票: pid -> [(user_idx, is_superuser), ...]
    vote_details: Dict[int, List[Tuple[int, bool]]] = {}
    total_selections = 0
    for result in batch_results:
        if result:
            for user_idx, pids in result.items():
                is_su = user_preferences[user_idx][1] if user_idx < len(user_preferences) else False
                for pid in pids:
                    if pid not in vote_details:
                        vote_details[pid] = []
                    vote_details[pid].append((user_idx, is_su))
                total_selections += len(pids)

    if not vote_details:
        logger.info("Vision 筛选: 所有批次均未返回有效结果")
        return None, {}

    # 排序：共识优先、超用户优先
    def sort_key(pid: int):
        details = vote_details[pid]
        count = len(details)
        has_su = any(is_su for _, is_su in details)
        first_su_idx = min((idx for idx, is_su in details if is_su), default=999)
        return (count, has_su, -first_su_idx)

    sorted_pids = sorted(vote_details.keys(), key=sort_key, reverse=True)

    logger.info(
        f"Vision 筛选完成: {len(batches)} 批, {total_selections} 次选择, "
        f"汇总 {len(vote_details)} 张不同作品"
    )

    return sorted_pids, vote_details


async def vision_filter_multi_group(
    images: List[Dict],
    group_preferences: Dict[int, List[Tuple[str, bool, str]]],
    target_count: int = 15,
) -> Dict[int, List[int]]:
    """
    跨群合并 vision 筛选：多个群共享一次图片下载和 API 调用。

    Args:
        images: 候选图片列表
        group_preferences: {group_id: [(pref_text, is_superuser, user_id), ...]}
        target_count: 每个群取前几张

    Returns:
        {group_id: [pid, ...]}  — 每个群筛选后的 PID 列表
    """
    if not group_preferences:
        return {}

    # 将所有群的用户平铺，记录 user_idx → group_id 映射
    flat_users: List[Tuple[str, bool, str]] = []
    user_group_map: Dict[int, int] = {}  # user_idx in flat list → group_id
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

    logger.info(
        f"Vision 跨群合并: {len(group_preferences)} 个群, {len(flat_users)} 个用户, "
        f"{len(images)} 张候选图"
    )

    # 一次 vision 筛选（图片下载在内部缓存复用）
    sorted_pids, vote_details = await vision_filter_images(images, flat_users)

    if not sorted_pids:
        return {}

    # 按群拆分投票明细
    group_votes: Dict[int, Dict[int, List[Tuple[int, bool]]]] = {
        gid: {} for gid in group_preferences
    }
    for pid, voters in vote_details.items():
        for user_idx, is_su in voters:
            gid = user_group_map.get(user_idx)
            if gid is not None:
                if pid not in group_votes[gid]:
                    group_votes[gid][pid] = []
                group_votes[gid][pid].append((user_idx, is_su))

    # 每个群独立排序
    def sort_key(pid: int, details: List[Tuple[int, bool]]):
        count = len(details)
        has_su = any(is_su for _, is_su in details)
        first_su_idx = min((idx for idx, is_su in details if is_su), default=999)
        return (count, has_su, -first_su_idx)

    results: Dict[int, List[int]] = {}
    for gid, votes in group_votes.items():
        if not votes:
            results[gid] = []
            continue
        g_sorted = sorted(
            votes.keys(),
            key=lambda pid: sort_key(pid, votes[pid]),
            reverse=True,
        )
        results[gid] = g_sorted[:target_count]
        logger.info(f"  群 {gid}: {len(g_sorted)} 张作品 → 取前 {target_count} 张")

    return results

