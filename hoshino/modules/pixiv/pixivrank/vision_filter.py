'''
Author: SheBot
Date: 2026-05-20
Description: Vision 视觉筛选 — 分批调用 vision 模型看图筛选图片
'''
import asyncio
import base64
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import httpx
from hoshino.log import logger

from .config import Config
from .profile_utils import extract_profile_for_filter

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


def _resolve_vision_api_config() -> Optional[Dict[str, Any]]:
    if not conf.vision_api_key:
        return None
    return {
        "api_base": conf.vision_api_base,
        "api_key": conf.vision_api_key,
        "model": conf.vision_model,
        "source": "pixivrank.vision",
    }


def is_vision_filter_available() -> bool:
    return _resolve_vision_api_config() is not None


def _safe_image_meta(img: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pid": img.get("pid"),
        "title": img.get("title", ""),
        "author": img.get("author", ""),
        "tags": img.get("tags", [])[:10],
    }


def _normalize_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:80] for item in value if item]


def _parse_selection_item(item: Any) -> Tuple[Optional[int], str, List[str], List[str]]:
    if isinstance(item, dict):
        raw_pid = item.get("pid")
        reason = str(item.get("reason", ""))[:300]
        matched = _normalize_string_list(item.get("matched", []))
        risks = _normalize_string_list(item.get("risks", []))
    else:
        raw_pid = item
        reason = ""
        matched = []
        risks = []

    try:
        return int(raw_pid), reason, matched, risks
    except (ValueError, TypeError):
        return None, reason, matched, risks


async def _call_vision_batch(
    batch_index: int,
    candidates: List[Dict[str, Any]],
    batch_images: List[Tuple[int, str]],  # [(pid, b64_data_url), ...]
    user_preferences: List[Tuple[str, bool, str]],  # [(pref_text, is_superuser, user_id), ...]
    select_per_user: int,
    api_config: Dict[str, Any],
) -> Tuple[Dict[int, List[int]], Dict[str, Any]]:
    """单批 vision 调用，返回 ({user_idx: [pid, ...]}, batch_log)"""
    batch_log: Dict[str, Any] = {
        "batch_index": batch_index,
        "candidates": [_safe_image_meta(img) for img in candidates],
        "downloaded_pids": [pid for pid, _ in batch_images],
        "raw_response": "",
        "parsed": {},
        "invalid_pids": [],
        "error": None,
    }

    # 构造用户画像文本
    user_texts = []
    for i, (pref, _is_su, uid) in enumerate(user_preferences):
        if not pref:
            continue
        profile = extract_profile_for_filter(pref)
        user_texts.append(
            f"【用户{i}】ID:{uid}\n用户画像:\n{profile}"
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

看构图、色调、风格、主题，匹配画像中的审美偏好。
只返回 JSON，不要输出隐藏推理或长篇思考。reason 写可审计的简短选择理由：
{{
  "user_0": [
    {{"pid": 123, "reason": "命中浅色发、泳装、精致完成度；无明显回避项", "matched": ["浅色发", "泳装"], "risks": []}}
  ],
  "user_1": []
}}"""

    api_base = api_config["api_base"].rstrip("/")
    api_key = api_config["api_key"]
    model = api_config["model"]

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
                ]
            }
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        batch_log["raw_response"] = content
        batch_log["usage"] = data.get("usage", {})

        # 解析 JSON
        json_str = content.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        try:
            result = json.loads(json_str.strip())
        except json.JSONDecodeError as e:
            batch_log["error"] = f"JSON 解析失败: {e}"
            return {}, batch_log

        # 构建返回: {user_idx: [pid, ...]}，同时记录可审计选择理由
        user_selections: Dict[int, List[int]] = {}
        valid_pids = {pid for pid, _ in batch_images}
        parsed_log: Dict[str, List[Dict[str, Any]]] = {}
        for i in range(len(user_preferences)):
            key = f"user_{i}"
            if key in result:
                pids = []
                parsed_log[key] = []
                if not isinstance(result[key], list):
                    continue
                for item in result[key]:
                    pid_int, reason, matched, risks = _parse_selection_item(item)
                    if pid_int is None:
                        continue
                    if pid_int not in valid_pids:
                        batch_log["invalid_pids"].append(pid_int)
                        continue
                    pids.append(pid_int)
                    parsed_log[key].append({
                        "pid": pid_int,
                        "reason": reason,
                        "matched": matched,
                        "risks": risks,
                    })
                if pids:
                    user_selections[i] = pids[:select_per_user]
                    parsed_log[key] = parsed_log[key][:select_per_user]

        batch_log["parsed"] = parsed_log
        return user_selections, batch_log


async def vision_filter_images(
    images: List[Dict],
    user_preferences: List[Tuple[str, bool, str]],
) -> Tuple[Optional[List[int]], Dict[int, List[Tuple[int, bool]]], Dict[str, Any]]:
    """
    分批调用 vision 模型筛选图片

    Args:
        images: 候选图片列表 [{"pid", "title", "author", "tags"}, ...]
        user_preferences: [(preference_text, is_superuser, user_id), ...]

    Returns:
        (排序后的 PID 列表, 投票明细 {pid: [(user_idx, is_superuser), ...]}, Vision 明细日志)
    """
    api_config = _resolve_vision_api_config()
    if not user_preferences or not api_config:
        return None, {}, {"error": "Vision API 未配置或无用户画像"}

    user_count = len(user_preferences)
    batch_size = conf.vision_batch_size
    select_per_user = conf.vision_select_per_user
    api_log = {
        "source": api_config.get("source", "unknown"),
        "api_base": api_config.get("api_base", ""),
        "model": api_config.get("model", ""),
    }
    vision_log: Dict[str, Any] = {
        "api": api_log,
        "batch_size": batch_size,
        "select_per_user": select_per_user,
        "users": [
            {
                "user_idx": idx,
                "user_id": uid,
                "is_superuser": is_su,
                "profile": extract_profile_for_filter(pref),
            }
            for idx, (pref, is_su, uid) in enumerate(user_preferences)
            if pref
        ],
        "batches": [],
        "vote_reasons": {},
        "sorted_pids": [],
    }

    logger.info(
        f"Vision 筛选开始: model={api_log['model']}, source={api_log['source']}, 用户={user_count}人, 候选={len(images)}张, "
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
    async def call_batch(
        batch_index: int,
        batch_images: List[Tuple[int, str]],
    ) -> Tuple[Dict[int, List[int]], Dict[str, Any]]:
        candidates = batches[batch_index]
        if len(batch_images) == 0:
            return {}, {
                "batch_index": batch_index,
                "candidates": [_safe_image_meta(img) for img in candidates],
                "downloaded_pids": [],
                "raw_response": "",
                "parsed": {},
                "invalid_pids": [],
                "error": "本批图片下载全部失败",
            }
        try:
            return await _call_vision_batch(batch_index, candidates, batch_images, user_preferences, select_per_user, api_config)
        except httpx.HTTPStatusError as e:
            logger.error(f"Vision API HTTP 错误: {e.response.status_code} - {e.response.text[:200]}")
            return {}, {
                "batch_index": batch_index,
                "candidates": [_safe_image_meta(img) for img in candidates],
                "downloaded_pids": [pid for pid, _ in batch_images],
                "raw_response": e.response.text[:1000],
                "parsed": {},
                "invalid_pids": [],
                "error": f"HTTP {e.response.status_code}",
            }
        except Exception as e:
            logger.exception(f"Vision API 调用失败: {e}")
            return {}, {
                "batch_index": batch_index,
                "candidates": [_safe_image_meta(img) for img in candidates],
                "downloaded_pids": [pid for pid, _ in batch_images],
                "raw_response": "",
                "parsed": {},
                "invalid_pids": [],
                "error": str(e),
            }

    batch_results = await asyncio.gather(*[
        call_batch(batch_index, batch_images)
        for batch_index, batch_images in enumerate(downloaded_batches)
    ])

    # 汇总投票: pid -> [(user_idx, is_superuser), ...]
    vote_details: Dict[int, List[Tuple[int, bool]]] = {}
    vote_reasons: Dict[int, List[Dict[str, Any]]] = {}
    total_selections = 0
    for result, batch_log in batch_results:
        vision_log["batches"].append(batch_log)
        if result:
            for user_idx, pids in result.items():
                is_su = user_preferences[user_idx][1] if user_idx < len(user_preferences) else False
                uid = user_preferences[user_idx][2] if user_idx < len(user_preferences) else ""
                parsed_items = {
                    item["pid"]: item
                    for item in batch_log.get("parsed", {}).get(f"user_{user_idx}", [])
                }
                for pid in pids:
                    if pid not in vote_details:
                        vote_details[pid] = []
                    if pid not in vote_reasons:
                        vote_reasons[pid] = []
                    vote_details[pid].append((user_idx, is_su))
                    item = parsed_items.get(pid, {})
                    vote_reasons[pid].append({
                        "user_idx": user_idx,
                        "user_id": uid,
                        "is_superuser": is_su,
                        "reason": item.get("reason", ""),
                        "matched": item.get("matched", []),
                        "risks": item.get("risks", []),
                    })
                total_selections += len(pids)

    if not vote_details:
        logger.info("Vision 筛选: 所有批次均未返回有效结果")
        vision_log["vote_reasons"] = {}
        return None, {}, vision_log

    def sort_key(pid: int):
        details = vote_details[pid]
        count = len(details)
        first_idx = min((idx for idx, _ in details), default=999)
        return (count, -first_idx)

    sorted_pids = sorted(vote_details.keys(), key=sort_key, reverse=True)
    vision_log["vote_reasons"] = {str(pid): items for pid, items in vote_reasons.items()}
    vision_log["sorted_pids"] = sorted_pids

    logger.info(
        f"Vision 筛选完成: {len(batches)} 批, {total_selections} 次选择, "
        f"汇总 {len(vote_details)} 张不同作品"
    )

    return sorted_pids, vote_details, vision_log


async def vision_filter_multi_group(
    images: List[Dict],
    group_preferences: Dict[int, List[Tuple[str, bool, str]]],
    target_count: int = 15,
) -> Tuple[Dict[int, List[int]], Dict[int, Dict[str, Any]]]:
    """
    跨群合并 vision 筛选：多个群共享一次图片下载和 API 调用。

    Args:
        images: 候选图片列表
        group_preferences: {group_id: [(pref_text, is_superuser, user_id), ...]}
        target_count: 每个群取前几张

    Returns:
        ({group_id: [pid, ...]}, {group_id: vision_log})  — 每个群筛选后的 PID 列表及日志
    """
    if not group_preferences:
        return {}, {}

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
        return {}, {}

    logger.info(
        f"Vision 跨群合并: {len(group_preferences)} 个群, {len(flat_users)} 个用户, "
        f"{len(images)} 张候选图"
    )

    # 一次 vision 筛选（图片下载在内部缓存复用）
    sorted_pids, vote_details, vision_log = await vision_filter_images(images, flat_users)

    if not sorted_pids:
        return {}, {}

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
        first_idx = min((idx for idx, _ in details), default=999)
        return (count, -first_idx)

    results: Dict[int, List[int]] = {}
    logs: Dict[int, Dict[str, Any]] = {}
    for gid, votes in group_votes.items():
        if not votes:
            results[gid] = []
            logs[gid] = {
                **vision_log,
                "group_id": gid,
                "group_sorted_pids": [],
                "group_vote_details": {},
            }
            continue
        g_sorted = sorted(
            votes.keys(),
            key=lambda pid: sort_key(pid, votes[pid]),
            reverse=True,
        )
        results[gid] = g_sorted[:target_count]
        logs[gid] = {
            **vision_log,
            "group_id": gid,
            "group_sorted_pids": results[gid],
            "group_vote_details": {
                str(pid): [
                    {"user_idx": idx, "is_superuser": is_su}
                    for idx, is_su in details
                ]
                for pid, details in votes.items()
            },
        }
        logger.info(f"  群 {gid}: {len(g_sorted)} 张作品 → 取前 {target_count} 张")

    return results, logs
