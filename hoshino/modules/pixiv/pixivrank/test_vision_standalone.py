#!/usr/bin/env python3
"""
Vision 评分独立测试 - 零依赖 bot 框架，直接测试核心逻辑

用法:
    cd /root/bot/shebot_nb2
    .venv/bin/python hoshino/modules/pixiv/pixivrank/test_vision_standalone.py
    .venv/bin/python hoshino/modules/pixiv/pixivrank/test_vision_standalone.py -n 15 -b 15 -u 2
    .venv/bin/python hoshino/modules/pixiv/pixivrank/test_vision_standalone.py --multi-group

数据: data/pixiv/pixiv_rank_r18.json
API:  data/config/pixivrank.json
"""
import argparse
import asyncio
import base64
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import aiohttp
import httpx


PROJECT = Path(__file__).resolve().parent.parent.parent.parent.parent
RANK_FILE = PROJECT / "data" / "pixiv" / "pixiv_rank_r18.json"
PIXIVRANK_CONF = PROJECT / "data" / "config" / "pixivrank.json"
PREF_DIR = PROJECT / "data" / "aichat" / "preferences"
CACHE_DIR = PROJECT / "data" / "pixiv" / "vision_cache"

UserPreference = Tuple[str, bool, str]
UserEntry = Tuple[int, str, bool, str]
ScoreItem = Dict[str, Any]
ScoreMatrix = Dict[int, Dict[int, ScoreItem]]


class _Config:
    vision_api_base = ""
    vision_api_key = ""
    vision_model = "grok-4.3"
    vision_source = ""
    vision_batch_size = 15
    vision_user_batch_size = 4
    vision_max_request_chars = 4000000
    vision_max_concurrency = 4
    vision_retry_count = 2
    vision_high_score_threshold = 70
    vision_low_score_threshold = 40
    vision_consensus_bonus = 5.0
    vision_low_penalty = 5.0
    vision_risk_penalty = 3.0


conf = _Config()
_image_cache: Dict[int, str] = {}


def _disk_cache_path(pid: int) -> Path:
    return CACHE_DIR / f"{pid}.b64.txt"


def _load_from_disk(pid: int) -> Optional[str]:
    p = _disk_cache_path(pid)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None


def _save_to_disk(pid: int, b64: str) -> None:
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
                    url_part = image_url.split("?")[0]
                    url_ext = os.path.splitext(url_part)[1].lower()
                    if url_ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                        ext = url_ext.lstrip(".")
                return f"data:image/{ext};base64,{base64.b64encode(image_data).decode('utf-8')}"
    except Exception:
        return None


async def _download_image_cached(pid: int, url: str) -> Optional[str]:
    if pid in _image_cache:
        return _image_cache[pid]
    b64 = _load_from_disk(pid)
    if b64:
        _image_cache[pid] = b64
        return b64
    b64 = await _download_image(url)
    if b64:
        _image_cache[pid] = b64
        _save_to_disk(pid, b64)
    return b64


def _extract_markdown_section(text: str, title_keywords: List[str]) -> str:
    lines = text.splitlines()
    collecting = False
    result: List[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and any(keyword in stripped for keyword in title_keywords):
            collecting = True
            continue
        if collecting and stripped.startswith("## "):
            break
        if collecting:
            result.append(line)

    return "\n".join(result).strip()


def _extract_profile_for_filter(pref: str, max_chars: int = 1200, fallback_chars: int = 800) -> str:
    sections = [
        _extract_markdown_section(pref, ["推荐摘要", "核心偏好摘要"]),
        _extract_markdown_section(pref, ["核心审美画像"]),
    ]
    content = "\n\n".join(section for section in sections if section)
    if not content:
        return pref[:fallback_chars].strip()
    return content[:max_chars].strip()


def _extract_profile_summary(pref: str, max_chars: int = 120) -> str:
    profile = _extract_profile_for_filter(pref, max_chars=max_chars, fallback_chars=max_chars)
    return " ".join(profile.split())[:max_chars]


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


def _normalize_risk_list(value: Any) -> List[str]:
    ignored_exact = {"无匹配", "不匹配", "低匹配", "数据不足", "无风险", "无明显风险", "none", "n/a"}
    ignored_prefixes = ("无匹配", "不匹配", "低匹配", "数据不足")
    risks = []
    for item in _normalize_string_list(value):
        normalized = item.strip().lower()
        if normalized in ignored_exact:
            continue
        if normalized.startswith(ignored_prefixes):
            continue
        if "无明显风险" in normalized or "无风险" in normalized:
            continue
        risks.append(item)
    return risks


def _clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (ValueError, TypeError):
        score = 0.0
    return max(0.0, min(100.0, score))


def _parse_score_item(item: Any) -> Tuple[Optional[int], Optional[ScoreItem]]:
    if not isinstance(item, dict):
        return None, None
    try:
        pid = int(item.get("pid"))
    except (ValueError, TypeError):
        return None, None
    return pid, {
        "pid": pid,
        "score": _clamp_score(item.get("score", 0)),
        "confidence": str(item.get("confidence", ""))[:40],
        "reason": str(item.get("reason", ""))[:300],
        "matched": _normalize_string_list(item.get("matched", [])),
        "risks": _normalize_risk_list(item.get("risks", [])),
    }


def _redact_api_key(api_key: str) -> str:
    if len(api_key) <= 10:
        return "***" if api_key else ""
    return f"{api_key[:6]}...{api_key[-4:]}"


def _summarize_image_url(url: str) -> str:
    if not url.startswith("data:image/"):
        return url
    mime = url.split(";base64,", 1)[0].replace("data:", "")
    return f"<{mime};base64 chars={len(url)}>"


def _sanitize_api_payload(value: Any) -> Any:
    if isinstance(value, dict):
        if "image_url" in value and isinstance(value["image_url"], dict):
            sanitized = dict(value)
            sanitized["image_url"] = {
                **value["image_url"],
                "url": _summarize_image_url(str(value["image_url"].get("url", ""))),
            }
            return sanitized
        return {key: _sanitize_api_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_api_payload(item) for item in value]
    return value


def _chunked(items: List[Any], size: int) -> List[List[Any]]:
    size = max(1, size)
    return [items[i:i + size] for i in range(0, len(items), size)]


def _split_downloaded_batch(
    source_batch_index: int,
    candidates: List[Dict[str, Any]],
    batch_images: List[Tuple[int, str]],
    max_request_chars: int,
) -> List[Tuple[int, List[Dict[str, Any]], List[Tuple[int, str]], int]]:
    if not batch_images:
        return [(source_batch_index, candidates, [], 0)]

    pid_to_candidate = {int(img["pid"]): img for img in candidates if img.get("pid") is not None}
    result: List[Tuple[int, List[Dict[str, Any]], List[Tuple[int, str]], int]] = []
    current_candidates: List[Dict[str, Any]] = []
    current_images: List[Tuple[int, str]] = []
    current_chars = 0

    for pid, b64_url in batch_images:
        image_chars = len(b64_url)
        if current_images and current_chars + image_chars > max_request_chars:
            result.append((source_batch_index, current_candidates, current_images, current_chars))
            current_candidates = []
            current_images = []
            current_chars = 0

        candidate = pid_to_candidate.get(pid)
        if candidate is not None:
            current_candidates.append(candidate)
        current_images.append((pid, b64_url))
        current_chars += image_chars

    if current_images:
        result.append((source_batch_index, current_candidates, current_images, current_chars))
    return result


def _merge_score_matrix(target: ScoreMatrix, source: ScoreMatrix) -> None:
    for pid, by_user in source.items():
        target.setdefault(pid, {}).update(by_user)


def _aggregate_score_matrix(
    score_matrix: ScoreMatrix,
    candidate_order: Dict[int, int],
    allowed_user_indices: Optional[Set[int]] = None,
) -> Tuple[List[int], Dict[int, Dict[str, Any]]]:
    aggregated: Dict[int, Dict[str, Any]] = {}
    for pid, by_user in score_matrix.items():
        per_user = []
        for user_idx, item in sorted(by_user.items()):
            if allowed_user_indices is not None and user_idx not in allowed_user_indices:
                continue
            per_user.append({
                "user_idx": user_idx,
                "user_id": item.get("user_id", ""),
                "score": item.get("score", 0),
                "confidence": item.get("confidence", ""),
                "reason": item.get("reason", ""),
                "matched": item.get("matched", []),
                "risks": item.get("risks", []),
            })
        if not per_user:
            continue

        scores = [float(item["score"]) for item in per_user]
        avg_score = sum(scores) / len(scores)
        high_count = sum(1 for score in scores if score >= conf.vision_high_score_threshold)
        low_count = sum(1 for score in scores if score <= conf.vision_low_score_threshold)
        risk_count = sum(1 for item in per_user if item.get("risks"))
        final_score = (
            avg_score
            + high_count * conf.vision_consensus_bonus
            - low_count * conf.vision_low_penalty
            - risk_count * conf.vision_risk_penalty
        )
        aggregated[pid] = {
            "pid": pid,
            "avg_score": round(avg_score, 2),
            "high_count": high_count,
            "low_count": low_count,
            "risk_count": risk_count,
            "score_count": len(scores),
            "final_score": round(final_score, 2),
            "per_user": per_user,
        }

    def sort_key(pid: int) -> Tuple[float, float, int, int, int, int]:
        item = aggregated[pid]
        order = candidate_order.get(pid, 999999)
        return (
            item["final_score"],
            item["avg_score"],
            item["high_count"],
            -item["low_count"],
            -item["risk_count"],
            -order,
        )

    sorted_pids = sorted(aggregated.keys(), key=sort_key, reverse=True)
    return sorted_pids, aggregated


async def _call_vision_score_batch(
    image_batch_index: int,
    user_batch_index: int,
    candidates: List[Dict[str, Any]],
    batch_images: List[Tuple[int, str]],
    user_entries: List[UserEntry],
) -> Tuple[ScoreMatrix, Dict[str, Any]]:
    batch_log: Dict[str, Any] = {
        "image_batch_index": image_batch_index,
        "user_batch_index": user_batch_index,
        "users": [
            {"user_idx": idx, "user_id": uid}
            for idx, _pref, _is_su, uid in user_entries
        ],
        "candidates": [_safe_image_meta(img) for img in candidates],
        "downloaded_pids": [pid for pid, _ in batch_images],
        "raw_response": "",
        "parsed_scores": {},
        "missing_scores": {},
        "invalid_pids": [],
        "retry_count": 0,
        "error": None,
    }

    user_texts = []
    for user_idx, pref, _is_su, uid in user_entries:
        if not pref:
            continue
        profile = _extract_profile_for_filter(pref)
        user_texts.append(f"【user_{user_idx}】ID:{uid}\n用户画像:\n{profile}")

    users_block = "\n\n".join(user_texts)
    pid_labels = [f"PID:{pid}" for pid, _ in batch_images]
    content_parts = [
        {
            "type": "text",
            "text": (
                f"候选图片 PID: {', '.join(pid_labels)}\n\n"
                f"【用户画像】\n{users_block}\n\n"
                f"以下是 {len(batch_images)} 张候选图片，每张图上方有 PID 标签。"
            )
        }
    ]
    for pid, b64_url in batch_images:
        content_parts.append({"type": "text", "text": f"\n--- PID:{pid} ---"})
        content_parts.append({"type": "image_url", "image_url": {"url": b64_url}})

    user_keys = ", ".join(f"user_{idx}" for idx, _pref, _is_su, _uid in user_entries)
    system_prompt = f"""你是图片推荐评分助手。根据每位用户的画像，为每张候选图片给出 0-100 的匹配分。

必须遵守：
- 只返回 JSON，不要输出隐藏推理或长篇解释。
- 返回键必须是这些用户键：{user_keys}
- 每个用户数组必须覆盖本批全部 PID，即使不喜欢也要给低分，不要省略。
- score 是 0-100 数字：90+ 强匹配，70-89 明确喜欢，50-69 尚可，30-49 弱匹配，0-29 明确不适合。
- confidence 只能是 high / medium / low。
- reason 写可审计的简短理由，matched 写命中的画像点，risks 写触发的回避或风险点。
- risks 只写与该用户画像中的回避项或限制冲突的内容，不要把候选池本身的成人/R18属性当作风险，除非画像明确回避。
- 不喜欢但没有明确回避冲突时 risks 必须为 []，不要写“无匹配”“低匹配”“数据不足”。
- 先依据用户画像的推荐摘要和核心审美画像评分，不要只按作品题材标签泛泛判断。

返回格式：
{{
  "user_0": [
    {{"pid": 123, "score": 82, "confidence": "medium", "reason": "命中浅色发、泳装、精致完成度", "matched": ["浅色发", "泳装"], "risks": []}}
  ]
}}"""

    api_base = conf.vision_api_base.rstrip("/")
    request_url = f"{api_base}/chat/completions"
    headers = {"Authorization": f"Bearer {conf.vision_api_key}", "Content-Type": "application/json"}
    payload = {
        "model": conf.vision_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_parts},
        ],
    }
    debug_headers = {
        "Authorization": f"Bearer {_redact_api_key(conf.vision_api_key)}",
        "Content-Type": headers["Content-Type"],
    }

    print(f"    POST {request_url}")
    print(f"    Model: {conf.vision_model}, 图片: {len(batch_images)}张, 用户: {len(user_entries)}人")
    print("    --- API 请求参数 ---")
    print(f"    URL: {request_url}")
    print(f"    Headers: {json.dumps(debug_headers, ensure_ascii=False)}")
    print(json.dumps(_sanitize_api_payload(payload), ensure_ascii=False, indent=2))
    print("    --- 请求参数结束 ---")

    async with httpx.AsyncClient(timeout=180.0) as client:
        for attempt in range(conf.vision_retry_count + 1):
            try:
                resp = await client.post(request_url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                batch_log["raw_response"] = content
                batch_log["usage"] = data.get("usage", {})
                batch_log["retry_count"] = attempt
                print(f"    Token: {json.dumps(data.get('usage', {}), ensure_ascii=False)}")
                print(f"    Model: {data.get('model', '?')}")
                print(f"    Finish: {data['choices'][0].get('finish_reason', '?')}")
                print("    --- API 返回 ---")
                print(f"    {content}")
                print("    --- 结束 ---")
                break
            except httpx.HTTPStatusError:
                raise
            except (httpx.TimeoutException, httpx.TransportError) as e:
                err = str(e) or type(e).__name__
                batch_log["error"] = f"{type(e).__name__}: {err[:200]}"
                batch_log["retry_count"] = attempt
                if attempt < conf.vision_retry_count:
                    wait_seconds = min(2 ** attempt, 5)
                    print(
                        f"    网络错误，准备重试 {attempt + 1}/{conf.vision_retry_count}: "
                        f"{type(e).__name__}"
                    )
                    await asyncio.sleep(wait_seconds)
                    continue
                print(f"    网络错误，本批放弃: 已重试={conf.vision_retry_count}, {type(e).__name__}: {err[:120]}")
                return {}, batch_log

    json_str = content.strip()
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0]
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0]
    try:
        result = json.loads(json_str.strip())
    except json.JSONDecodeError as e:
        batch_log["error"] = f"JSON解析失败: {e}"
        return {}, batch_log

    if not isinstance(result, dict):
        batch_log["error"] = "JSON 根对象不是 dict"
        return {}, batch_log

    valid_pids = {pid for pid, _ in batch_images}
    score_matrix: ScoreMatrix = {}
    for user_idx, _pref, is_su, uid in user_entries:
        key = f"user_{user_idx}"
        raw_items = result.get(key, [])
        parsed_items: List[Dict[str, Any]] = []
        returned_pids: Set[int] = set()
        if not isinstance(raw_items, list):
            batch_log["missing_scores"][key] = sorted(valid_pids)
            continue
        for raw_item in raw_items:
            pid, score_item = _parse_score_item(raw_item)
            if pid is None or score_item is None:
                continue
            if pid not in valid_pids:
                batch_log["invalid_pids"].append(pid)
                continue
            returned_pids.add(pid)
            score_item["user_idx"] = user_idx
            score_item["user_id"] = uid
            score_item["is_superuser"] = is_su
            score_matrix.setdefault(pid, {})[user_idx] = score_item
            parsed_items.append(score_item)
        missing = sorted(valid_pids - returned_pids)
        if missing:
            batch_log["missing_scores"][key] = missing
        batch_log["parsed_scores"][key] = parsed_items

    return score_matrix, batch_log


async def vision_filter_images(
    images: List[Dict],
    user_preferences: List[UserPreference],
) -> Tuple[Optional[List[int]], ScoreMatrix, Dict[str, Any]]:
    if not user_preferences or not conf.vision_api_key:
        return None, {}, {"error": "Vision API未配置或无用户画像"}

    user_entries: List[UserEntry] = [
        (idx, pref, is_su, uid)
        for idx, (pref, is_su, uid) in enumerate(user_preferences)
        if pref
    ]
    if not user_entries:
        return None, {}, {"error": "无有效用户画像"}

    candidate_order = {
        int(img["pid"]): idx
        for idx, img in enumerate(images)
        if img.get("pid") is not None
    }
    vision_log: Dict[str, Any] = {
        "mode": "score_matrix",
        "api": {
            "source": conf.vision_source or "pixivrank.vision",
            "api_base": conf.vision_api_base,
            "model": conf.vision_model,
        },
        "batch_size": conf.vision_batch_size,
        "user_batch_size": conf.vision_user_batch_size,
        "max_request_chars": conf.vision_max_request_chars,
        "max_concurrency": conf.vision_max_concurrency,
        "retry_count": conf.vision_retry_count,
        "thresholds": {
            "high_score": conf.vision_high_score_threshold,
            "low_score": conf.vision_low_score_threshold,
            "consensus_bonus": conf.vision_consensus_bonus,
            "low_penalty": conf.vision_low_penalty,
            "risk_penalty": conf.vision_risk_penalty,
        },
        "users": [
            {
                "user_idx": idx,
                "user_id": uid,
                "is_superuser": is_su,
                "profile": _extract_profile_for_filter(pref),
            }
            for idx, pref, is_su, uid in user_entries
        ],
        "batches": [],
        "scores": {},
        "sorted_pids": [],
    }

    print(
        f"Vision 评分: model={conf.vision_model}, source={vision_log['api']['source']}, "
        f"{len(user_entries)}用户, {len(images)}张图, "
        f"图片批{conf.vision_batch_size}张, 用户批{conf.vision_user_batch_size}人, "
        f"请求图像上限={conf.vision_max_request_chars} chars, 并发{conf.vision_max_concurrency}"
    )

    image_batches = _chunked(images, conf.vision_batch_size)
    user_batches = _chunked(user_entries, conf.vision_user_batch_size)
    print(f"分 {len(image_batches)} 个图片批 × {len(user_batches)} 个用户批，开始下载...")

    async def download_batch(batch: List[Dict]) -> List[Tuple[int, str]]:
        async def download_one(img: Dict) -> Optional[Tuple[int, str]]:
            url = img.get("url", "")
            if not url:
                url = f"https://pixiv.shewinder.win/img/{img['pid']}"
            else:
                url = url.replace("i.pximg.net", "pixiv.shewinder.win")
            b64 = await _download_image_cached(img["pid"], url)
            if b64:
                return (img["pid"], b64)
            print(f"    下载失败 PID:{img['pid']}")
            return None

        results = await asyncio.gather(*[download_one(img) for img in batch])
        return [r for r in results if r is not None]

    downloaded_batches = await asyncio.gather(*[download_batch(batch) for batch in image_batches])
    total_downloaded = sum(len(batch) for batch in downloaded_batches)
    print(f"下载完成: {total_downloaded}/{len(images)} 张, 缓存数量: {len(_image_cache)}")
    image_request_batches: List[Tuple[int, List[Dict[str, Any]], List[Tuple[int, str]], int]] = []
    for source_batch_index, (candidates, batch_images) in enumerate(zip(image_batches, downloaded_batches)):
        image_request_batches.extend(
            _split_downloaded_batch(
                source_batch_index,
                candidates,
                batch_images,
                max(1, conf.vision_max_request_chars),
            )
        )
    print(
        f"图片批拆分: 原始图片批={len(image_batches)}, 请求图片批={len(image_request_batches)}, "
        f"max_request_chars={conf.vision_max_request_chars}"
    )
    api_semaphore = asyncio.Semaphore(max(1, conf.vision_max_concurrency))

    async def call_batch(
        request_batch_index: int,
        source_batch_index: int,
        user_batch_index: int,
        candidates: List[Dict[str, Any]],
        batch_images: List[Tuple[int, str]],
        batch_chars: int,
        user_batch: List[UserEntry],
    ) -> Tuple[ScoreMatrix, Dict[str, Any]]:
        if not batch_images:
            return {}, {
                "image_batch_index": request_batch_index,
                "source_image_batch_index": source_batch_index,
                "user_batch_index": user_batch_index,
                "users": [{"user_idx": idx, "user_id": uid} for idx, _pref, _is_su, uid in user_batch],
                "candidates": [_safe_image_meta(img) for img in candidates],
                "downloaded_pids": [],
                "image_chars": batch_chars,
                "max_request_chars": conf.vision_max_request_chars,
                "raw_response": "",
                "parsed_scores": {},
                "missing_scores": {},
                "invalid_pids": [],
                "retry_count": 0,
                "error": "本批图片下载全部失败",
            }
        try:
            async with api_semaphore:
                return await _call_vision_score_batch(
                    request_batch_index,
                    user_batch_index,
                    candidates,
                    batch_images,
                    user_batch,
                )
        except httpx.HTTPStatusError as e:
            print(f"    HTTP {e.response.status_code}: {e.response.text[:200]}")
            return {}, {
                "image_batch_index": request_batch_index,
                "source_image_batch_index": source_batch_index,
                "user_batch_index": user_batch_index,
                "users": [{"user_idx": idx, "user_id": uid} for idx, _pref, _is_su, uid in user_batch],
                "candidates": [_safe_image_meta(img) for img in candidates],
                "downloaded_pids": [pid for pid, _ in batch_images],
                "image_chars": batch_chars,
                "max_request_chars": conf.vision_max_request_chars,
                "raw_response": e.response.text[:1000],
                "parsed_scores": {},
                "missing_scores": {},
                "invalid_pids": [],
                "retry_count": 0,
                "error": f"HTTP {e.response.status_code}",
            }
        except Exception as e:
            print(f"    API调用失败: {e}")
            return {}, {
                "image_batch_index": request_batch_index,
                "source_image_batch_index": source_batch_index,
                "user_batch_index": user_batch_index,
                "users": [{"user_idx": idx, "user_id": uid} for idx, _pref, _is_su, uid in user_batch],
                "candidates": [_safe_image_meta(img) for img in candidates],
                "downloaded_pids": [pid for pid, _ in batch_images],
                "image_chars": batch_chars,
                "max_request_chars": conf.vision_max_request_chars,
                "raw_response": "",
                "parsed_scores": {},
                "missing_scores": {},
                "invalid_pids": [],
                "error": str(e),
            }

    tasks = [
        call_batch(
            request_batch_index,
            source_batch_index,
            user_batch_index,
            candidates,
            batch_images,
            batch_chars,
            user_batch,
        )
        for request_batch_index, (source_batch_index, candidates, batch_images, batch_chars)
        in enumerate(image_request_batches)
        for user_batch_index, user_batch in enumerate(user_batches)
    ]
    batch_results = await asyncio.gather(*tasks)

    score_matrix: ScoreMatrix = {}
    total_scores = 0
    for partial_matrix, batch_log in batch_results:
        vision_log["batches"].append(batch_log)
        _merge_score_matrix(score_matrix, partial_matrix)
        total_scores += sum(len(by_user) for by_user in partial_matrix.values())
    vision_log["call_count"] = len(batch_results)
    vision_log["total_scores"] = total_scores

    sorted_pids, aggregated = _aggregate_score_matrix(score_matrix, candidate_order)
    if not sorted_pids:
        print("所有批均未返回有效评分")
        return None, {}, vision_log

    vision_log["scores"] = {str(pid): item for pid, item in aggregated.items()}
    vision_log["sorted_pids"] = sorted_pids
    print(f"汇总: {len(score_matrix)} 张作品有评分\n")
    return sorted_pids, score_matrix, vision_log


async def vision_filter_multi_group(
    images: List[Dict],
    group_preferences: Dict[int, List[UserPreference]],
    target_count: int = 15,
) -> Tuple[Dict[int, List[int]], Dict[int, Dict[str, Any]]]:
    if not group_preferences:
        return {}, {}

    flat_users: List[UserPreference] = []
    group_user_indices: Dict[int, Set[int]] = {gid: set() for gid in group_preferences}
    idx = 0
    for gid, prefs in group_preferences.items():
        for pref, is_su, uid in prefs:
            if not pref:
                continue
            flat_users.append((pref, is_su, uid))
            group_user_indices.setdefault(gid, set()).add(idx)
            idx += 1

    if not flat_users:
        return {}, {}

    print(f"跨群合并: {len(group_preferences)}群, {len(flat_users)}用户, {len(images)}张图")
    sorted_pids, score_matrix, vision_log = await vision_filter_images(images, flat_users)
    if not sorted_pids:
        return {}, {}

    candidate_order = {
        int(img["pid"]): idx
        for idx, img in enumerate(images)
        if img.get("pid") is not None
    }
    results: Dict[int, List[int]] = {}
    logs: Dict[int, Dict[str, Any]] = {}
    all_users = vision_log.get("users", [])
    for gid, allowed_indices in group_user_indices.items():
        group_sorted, group_scores = _aggregate_score_matrix(
            score_matrix,
            candidate_order,
            allowed_user_indices=allowed_indices,
        )
        results[gid] = group_sorted[:target_count]
        logs[gid] = {
            **vision_log,
            "group_id": gid,
            "users": [
                user for user in all_users
                if user.get("user_idx") in allowed_indices
            ],
            "scores": {str(pid): item for pid, item in group_scores.items()},
            "sorted_pids": group_sorted,
            "group_sorted_pids": results[gid],
        }
        print(f"  群{gid}: {len(group_sorted)} 张有评分 → 取前{target_count}张")
    return results, logs


def load_config() -> None:
    data = json.loads(PIXIVRANK_CONF.read_text())
    conf.vision_api_base = data.get("vision_api_base", "")
    conf.vision_api_key = data.get("vision_api_key", "")
    conf.vision_model = data.get("vision_model", conf.vision_model)
    conf.vision_batch_size = data.get("vision_batch_size", conf.vision_batch_size)
    conf.vision_user_batch_size = data.get("vision_user_batch_size", conf.vision_user_batch_size)
    conf.vision_max_request_chars = data.get("vision_max_request_chars", conf.vision_max_request_chars)
    conf.vision_max_concurrency = data.get("vision_max_concurrency", conf.vision_max_concurrency)
    conf.vision_retry_count = data.get("vision_retry_count", conf.vision_retry_count)
    conf.vision_high_score_threshold = data.get("vision_high_score_threshold", conf.vision_high_score_threshold)
    conf.vision_low_score_threshold = data.get("vision_low_score_threshold", conf.vision_low_score_threshold)
    conf.vision_consensus_bonus = data.get("vision_consensus_bonus", conf.vision_consensus_bonus)
    conf.vision_low_penalty = data.get("vision_low_penalty", conf.vision_low_penalty)
    conf.vision_risk_penalty = data.get("vision_risk_penalty", conf.vision_risk_penalty)
    conf.vision_source = "pixivrank.vision"
    if not conf.vision_api_key:
        raise RuntimeError("pixivrank Vision API 未配置")
    print(f"API : pixivrank.vision | {conf.vision_api_base}")
    print(f"Model: {conf.vision_model}")


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


def load_preferences(count: int) -> List[UserPreference]:
    result: List[UserPreference] = []
    if PREF_DIR.exists():
        for f in sorted(PREF_DIR.glob("*.md"))[:count]:
            content = f.read_text(encoding="utf-8").strip()
            if content:
                result.append((content, False, f.stem))
    while len(result) < count:
        i = len(result)
        sample = (
            "## 核心审美画像\n"
            f"测试用户{i}: 偏好冷色调、几何构图、光影对比强烈的作品。"
            "偏好科幻/赛博朋克/未来主义主题。回避甜腻幼化风格。\n"
        )
        result.append((sample, False, f"test_{i}"))
    return result


async def main() -> None:
    ap = argparse.ArgumentParser(description="Vision 评分独立测试")
    ap.add_argument("-n", "--images", type=int, default=15, help="图片数量 (默认15)")
    ap.add_argument("-b", "--batch", type=int, default=15, help="每批图片数量 (默认15)")
    ap.add_argument("-u", "--users", type=int, default=3, help="用户数 (默认3)")
    ap.add_argument("--user-batch", type=int, default=4, help="每批用户数 (默认4)")
    ap.add_argument("--max-request-chars", type=int, default=4000000, help="单个请求图像base64字符上限")
    ap.add_argument("--concurrency", type=int, default=4, help="API并发数 (默认4)")
    ap.add_argument("--retries", type=int, default=2, help="网络错误重试次数 (默认2)")
    ap.add_argument("--multi-group", action="store_true", help="测试跨群合并")
    ap.add_argument("--dry-run", action="store_true", help="仅下载图片不调API")
    ap.add_argument("--clear-cache", action="store_true", help="清除磁盘缓存后重新下载")
    args = ap.parse_args()

    print("=" * 60)
    print("Vision 评分独立测试")
    print("=" * 60)

    load_config()
    images = load_images(args.images)
    conf.vision_batch_size = args.batch
    conf.vision_user_batch_size = args.user_batch
    conf.vision_max_request_chars = args.max_request_chars
    conf.vision_max_concurrency = args.concurrency
    conf.vision_retry_count = args.retries
    user_prefs = load_preferences(args.users)

    print(
        f"测试参数: 图片={len(images)}张, 图片批={args.batch}张, "
        f"用户={len(user_prefs)}人, 用户批={args.user_batch}人, 并发={args.concurrency}"
    )
    for pref, _is_su, uid in user_prefs:
        summary = _extract_profile_summary(pref)
        print(f"  {uid}: {summary[:80]}...")
    print()

    if args.clear_cache:
        if CACHE_DIR.exists():
            shutil.rmtree(CACHE_DIR)
            print(f"已清除磁盘缓存: {CACHE_DIR}\n")
        else:
            print("磁盘缓存为空\n")

    disk_cached = len(list(CACHE_DIR.glob("*.txt"))) if CACHE_DIR.exists() else 0
    print(f"磁盘缓存: {disk_cached} 张\n")

    if args.dry_run:
        print("--- Dry Run: 仅下载图片 ---")
        _image_cache.clear()
        tasks = [
            _download_image_cached(img["pid"], img["url"].replace("i.pximg.net", "pixiv.shewinder.win"))
            for img in images
        ]
        results = await asyncio.gather(*tasks)
        ok = sum(1 for r in results if r)
        new_disk = len(list(CACHE_DIR.glob("*.txt"))) - disk_cached if CACHE_DIR.exists() else 0
        print(f"结果: {ok}/{len(images)} 张 (新缓存 {max(0, new_disk)} 张)\n")
        return

    _image_cache.clear()
    print("--- 单群 Vision 评分 ---")
    selected, _score_matrix, vision_log = await vision_filter_images(images, user_prefs)
    selected = selected or []

    print(f"结果: {len(selected)} 张有评分\n")
    for pid in selected[:15]:
        img = next((i for i in images if i["pid"] == pid), None)
        title = img["title"][:40] if img else "?"
        score_info = vision_log.get("scores", {}).get(str(pid), {})
        print(
            f"  PID:{pid:>10}  final={score_info.get('final_score')} "
            f"avg={score_info.get('avg_score')} high={score_info.get('high_count')} "
            f"low={score_info.get('low_count')} risk={score_info.get('risk_count')}  {title}"
        )
        for item in score_info.get("per_user", []):
            matched = ", ".join(item.get("matched", []))
            risks = ", ".join(item.get("risks", []))
            print(f"               u{item.get('user_idx')} score={item.get('score')}: {item.get('reason', '')}")
            if matched:
                print(f"               命中: {matched}")
            if risks:
                print(f"               风险: {risks}")

    if args.multi_group:
        print("\n--- 跨群合并 (2个群) ---")
        _image_cache.clear()
        group_prefs = {10001: user_prefs[:2], 10002: user_prefs[2:]}
        group_pids, group_logs = await vision_filter_multi_group(images, group_prefs)
        for gid, pids in group_pids.items():
            print(f"  群{gid}: {len(pids)} 张  {pids[:5]}...")
            first_pid = pids[0] if pids else None
            if first_pid:
                score_info = group_logs.get(gid, {}).get("scores", {}).get(str(first_pid), {})
                print(f"    首图 final_score: {score_info.get('final_score')}")

    print(f"\n{'=' * 60}")
    print("测试完成")


if __name__ == "__main__":
    asyncio.run(main())
