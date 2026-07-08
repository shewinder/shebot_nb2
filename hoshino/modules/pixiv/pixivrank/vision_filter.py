'''
Author: SheBot
Date: 2026-05-20
Description: Vision 视觉筛选 - 分批调用 vision 模型为图片打分排序
'''
import asyncio
import base64
import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple

import aiohttp
import httpx
from hoshino.log import logger

from .config import Config
from .profile_utils import extract_profile_for_filter

conf = Config.get_instance("pixivrank")

UserPreference = Tuple[str, bool, str]
UserEntry = Tuple[int, str, bool, str]
ScoreItem = Dict[str, Any]
ScoreMatrix = Dict[int, Dict[int, ScoreItem]]

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


def _format_candidate_meta(candidates: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for img in candidates:
        pid = img.get("pid")
        title = str(img.get("title", ""))[:80]
        author = str(img.get("author", ""))[:40]
        tags = [str(tag)[:40] for tag in img.get("tags", [])[:12] if tag]
        tags_text = ", ".join(tags) if tags else "无"
        lines.append(f"PID:{pid} | 标题:{title} | 作者:{author} | 标签:{tags_text}")
    return "\n".join(lines)


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

    score_item: ScoreItem = {
        "pid": pid,
        "score": _clamp_score(item.get("score", 0)),
        "confidence": str(item.get("confidence", ""))[:40],
        "reason": str(item.get("reason", ""))[:300],
        "matched": _normalize_string_list(item.get("matched", [])),
        "risks": _normalize_risk_list(item.get("risks", [])),
    }
    return pid, score_item


def _build_vision_system_prompt(user_keys: str) -> str:
    return f"""你是图片推荐评分助手。根据每位用户的画像，为每张候选图片给出 0-100 的匹配分。

必须遵守：
- 只返回 JSON，不要输出隐藏推理或长篇解释。
- 返回键必须是这些用户键：{user_keys}
- 每个用户数组必须覆盖本批全部 PID，即使不喜欢也要给低分，不要省略。
- score 是 0-100 数字：90+ 强匹配，70-89 明确喜欢，50-69 尚可，30-49 弱匹配，0-29 明确不适合。
- confidence 只能是 high / medium / low。
- reason 写可审计的简短理由，matched 写命中的画像点，risks 写触发的回避或风险点。

评分顺序：
1. 先判断整张图为什么吸引或劝退用户：整体美感、完成度、角色/主体设计、构图、氛围是否成立。
2. 再判断题材与关系语义：图片、标题、标签若显示高负载/粗暴/猎奇/非合意/不适元素堆叠等内容，必须评估它是否破坏用户画像里的审美距离。
3. 最后才看发色、瞳色、服装、IP、道具、单个姿势等浅层线索。除非画像明确把它们写成强偏好，否则只能作为弱到中等证据。
4. 如果画像明确说某类线索“不作为约束”或“只是视觉线索”，不得因为候选图缺少这些线索而降分，也不得因为命中这些线索而高分。
5. IP、标题和 tags 是识别题材语义的辅助信息，不能代替对图片整体美感和用户画像的判断。

matched / risks 规则：
- matched 优先写综合审美点，例如“高完成度”“角色设计精致”“构图有美学距离”“关系氛围匹配”“美学化身体线条”，不要默认写成发色/服装/IP 标签列表。
- risks 只写与该用户画像中的回避项、降权项或边界条件冲突的内容。
- 不要把候选池本身的成人/R18属性当作风险，除非画像明确回避相应表达方式。
- 不喜欢但没有明确回避冲突时 risks 必须为 []，不要写“无匹配”“低匹配”“数据不足”。

返回格式：
{{
  "user_0": [
    {{"pid": 123, "score": 82, "confidence": "medium", "reason": "整体完成度高，角色设计和构图有美学距离，成人表达未压过角色魅力", "matched": ["高完成度", "角色整体美感", "构图有美学距离"], "risks": []}}
  ]
}}"""


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
        if pid not in target:
            target[pid] = {}
        target[pid].update(by_user)


def _aggregate_score_matrix(
    score_matrix: ScoreMatrix,
    candidate_order: Dict[int, int],
    allowed_user_indices: Optional[Set[int]] = None,
) -> Tuple[List[int], Dict[int, Dict[str, Any]]]:
    aggregated: Dict[int, Dict[str, Any]] = {}
    high_threshold = getattr(conf, "vision_high_score_threshold", 70)
    low_threshold = getattr(conf, "vision_low_score_threshold", 40)
    consensus_bonus = getattr(conf, "vision_consensus_bonus", 5.0)
    low_penalty = getattr(conf, "vision_low_penalty", 5.0)
    risk_penalty = getattr(conf, "vision_risk_penalty", 3.0)

    for pid, by_user in score_matrix.items():
        per_user = []
        for user_idx, item in sorted(by_user.items()):
            if allowed_user_indices is not None and user_idx not in allowed_user_indices:
                continue
            per_user.append({
                "user_idx": user_idx,
                "user_id": item.get("user_id", ""),
                "is_superuser": item.get("is_superuser", False),
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
        high_count = sum(1 for score in scores if score >= high_threshold)
        low_count = sum(1 for score in scores if score <= low_threshold)
        risk_count = sum(1 for item in per_user if item.get("risks"))
        final_score = (
            avg_score
            + high_count * consensus_bonus
            - low_count * low_penalty
            - risk_count * risk_penalty
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
    api_config: Dict[str, Any],
) -> Tuple[ScoreMatrix, Dict[str, Any]]:
    batch_log: Dict[str, Any] = {
        "image_batch_index": image_batch_index,
        "user_batch_index": user_batch_index,
        "users": [
            {"user_idx": idx, "user_id": uid, "is_superuser": is_su}
            for idx, _pref, is_su, uid in user_entries
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
        profile = extract_profile_for_filter(pref)
        user_texts.append(f"【user_{user_idx}】ID:{uid}\n用户画像:\n{profile}")

    users_block = "\n\n".join(user_texts)
    pid_labels = [f"PID:{pid}" for pid, _ in batch_images]
    candidate_meta = _format_candidate_meta(candidates)

    content_parts = [
        {
            "type": "text",
            "text": (
                f"候选图片 PID: {', '.join(pid_labels)}\n\n"
                f"【用户画像】\n{users_block}\n\n"
                f"【候选元数据】\n"
                f"标题和标签只作为识别题材语义的辅助线索，不要用它们替代图片整体判断。\n"
                f"{candidate_meta}\n\n"
                f"以下是 {len(batch_images)} 张候选图片，每张图上方有 PID 标签。"
            )
        }
    ]

    for pid, b64_url in batch_images:
        content_parts.append({"type": "text", "text": f"\n--- PID:{pid} ---"})
        content_parts.append({"type": "image_url", "image_url": {"url": b64_url}})

    user_keys = ", ".join(f"user_{idx}" for idx, _pref, _is_su, _uid in user_entries)
    system_prompt = _build_vision_system_prompt(user_keys)

    api_base = api_config["api_base"].rstrip("/")
    api_key = api_config["api_key"]
    model = api_config["model"]
    request_url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_parts},
        ],
    }
    retry_count = max(0, getattr(conf, "vision_retry_count", 2))

    async with httpx.AsyncClient(timeout=180.0) as client:
        for attempt in range(retry_count + 1):
            try:
                resp = await client.post(request_url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                batch_log["raw_response"] = content
                batch_log["usage"] = data.get("usage", {})
                batch_log["retry_count"] = attempt
                break
            except httpx.HTTPStatusError:
                raise
            except (httpx.TimeoutException, httpx.TransportError) as e:
                err = str(e) or type(e).__name__
                batch_log["error"] = f"{type(e).__name__}: {err[:200]}"
                batch_log["retry_count"] = attempt
                if attempt < retry_count:
                    wait_seconds = min(2 ** attempt, 5)
                    logger.warning(
                        f"Vision API 网络错误，准备重试 {attempt + 1}/{retry_count}: "
                        f"图片批={image_batch_index}, 用户批={user_batch_index}, error={type(e).__name__}"
                    )
                    await asyncio.sleep(wait_seconds)
                    continue
                logger.warning(
                    f"Vision API 网络错误，本批放弃: 图片批={image_batch_index}, 用户批={user_batch_index}, "
                    f"已重试={retry_count}, error={type(e).__name__}: {err[:120]}"
                )
                return {}, batch_log

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

    if not isinstance(result, dict):
        batch_log["error"] = "JSON 根对象不是 dict"
        return {}, batch_log

    score_matrix: ScoreMatrix = {}
    valid_pids = {pid for pid, _ in batch_images}
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
            if pid not in score_matrix:
                score_matrix[pid] = {}
            score_matrix[pid][user_idx] = score_item
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
    """
    分批调用 vision 模型为图片打分排序。

    Returns:
        (排序后的 PID 列表, 评分矩阵 {pid: {user_idx: score_item}}, Vision 明细日志)
    """
    api_config = _resolve_vision_api_config()
    if not user_preferences or not api_config:
        return None, {}, {"error": "Vision API 未配置或无用户画像"}

    user_entries: List[UserEntry] = [
        (idx, pref, is_su, uid)
        for idx, (pref, is_su, uid) in enumerate(user_preferences)
        if pref
    ]
    if not user_entries:
        return None, {}, {"error": "无有效用户画像"}

    batch_size = max(1, conf.vision_batch_size)
    user_batch_size = max(1, getattr(conf, "vision_user_batch_size", 4))
    max_request_chars = max(1, getattr(conf, "vision_max_request_chars", 4000000))
    max_concurrency = max(1, getattr(conf, "vision_max_concurrency", 4))
    candidate_order = {
        int(img["pid"]): idx
        for idx, img in enumerate(images)
        if img.get("pid") is not None
    }
    api_log = {
        "source": api_config.get("source", "unknown"),
        "api_base": api_config.get("api_base", ""),
        "model": api_config.get("model", ""),
    }
    thresholds = {
        "high_score": getattr(conf, "vision_high_score_threshold", 70),
        "low_score": getattr(conf, "vision_low_score_threshold", 40),
        "consensus_bonus": getattr(conf, "vision_consensus_bonus", 5.0),
        "low_penalty": getattr(conf, "vision_low_penalty", 5.0),
        "risk_penalty": getattr(conf, "vision_risk_penalty", 3.0),
    }
    vision_log: Dict[str, Any] = {
        "mode": "score_matrix",
        "api": api_log,
        "batch_size": batch_size,
        "user_batch_size": user_batch_size,
        "max_request_chars": max_request_chars,
        "max_concurrency": max_concurrency,
        "retry_count": getattr(conf, "vision_retry_count", 2),
        "thresholds": thresholds,
        "users": [
            {
                "user_idx": idx,
                "user_id": uid,
                "is_superuser": is_su,
                "profile": extract_profile_for_filter(pref),
            }
            for idx, pref, is_su, uid in user_entries
        ],
        "batches": [],
        "scores": {},
        "sorted_pids": [],
    }

    logger.info(
        f"Vision 评分开始: model={api_log['model']}, source={api_log['source']}, "
        f"用户={len(user_entries)}人, 候选={len(images)}张, "
        f"图片批={batch_size}张, 用户批={user_batch_size}人, "
        f"请求图像上限={max_request_chars} chars, 并发={max_concurrency}"
    )

    image_batches = _chunked(images, batch_size)
    user_batches = _chunked(user_entries, user_batch_size)
    logger.info(f"分 {len(image_batches)} 个图片批 × {len(user_batches)} 个用户批，开始下载和评分")

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
            logger.warning(f"Vision 评分: 图片下载失败 PID:{img['pid']}")
            return None

        results = await asyncio.gather(*[download_one(img) for img in batch])
        return [r for r in results if r is not None]

    downloaded_batches = await asyncio.gather(*[download_batch(batch) for batch in image_batches])
    image_request_batches: List[Tuple[int, List[Dict[str, Any]], List[Tuple[int, str]], int]] = []
    for source_batch_index, (candidates, batch_images) in enumerate(zip(image_batches, downloaded_batches)):
        image_request_batches.extend(
            _split_downloaded_batch(source_batch_index, candidates, batch_images, max_request_chars)
        )
    logger.info(
        f"Vision 图片批拆分: 原始图片批={len(image_batches)}, 请求图片批={len(image_request_batches)}, "
        f"max_request_chars={max_request_chars}"
    )
    api_semaphore = asyncio.Semaphore(max_concurrency)

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
                "users": [
                    {"user_idx": idx, "user_id": uid, "is_superuser": is_su}
                    for idx, _pref, is_su, uid in user_batch
                ],
                "candidates": [_safe_image_meta(img) for img in candidates],
                "downloaded_pids": [],
                "image_chars": batch_chars,
                "max_request_chars": max_request_chars,
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
                    api_config,
                )
        except httpx.HTTPStatusError as e:
            logger.error(f"Vision API HTTP 错误: {e.response.status_code} - {e.response.text[:200]}")
            return {}, {
                "image_batch_index": request_batch_index,
                "source_image_batch_index": source_batch_index,
                "user_batch_index": user_batch_index,
                "users": [
                    {"user_idx": idx, "user_id": uid, "is_superuser": is_su}
                    for idx, _pref, is_su, uid in user_batch
                ],
                "candidates": [_safe_image_meta(img) for img in candidates],
                "downloaded_pids": [pid for pid, _ in batch_images],
                "image_chars": batch_chars,
                "max_request_chars": max_request_chars,
                "raw_response": e.response.text[:1000],
                "parsed_scores": {},
                "missing_scores": {},
                "invalid_pids": [],
                "retry_count": 0,
                "error": f"HTTP {e.response.status_code}",
            }
        except Exception as e:
            logger.exception(f"Vision API 调用失败: {e}")
            return {}, {
                "image_batch_index": request_batch_index,
                "source_image_batch_index": source_batch_index,
                "user_batch_index": user_batch_index,
                "users": [
                    {"user_idx": idx, "user_id": uid, "is_superuser": is_su}
                    for idx, _pref, is_su, uid in user_batch
                ],
                "candidates": [_safe_image_meta(img) for img in candidates],
                "downloaded_pids": [pid for pid, _ in batch_images],
                "image_chars": batch_chars,
                "max_request_chars": max_request_chars,
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
        logger.info("Vision 评分: 所有批次均未返回有效评分")
        return None, {}, vision_log

    vision_log["scores"] = {str(pid): item for pid, item in aggregated.items()}
    vision_log["sorted_pids"] = sorted_pids

    logger.info(
        f"Vision 评分完成: {len(batch_results)} 次调用, {total_scores} 条评分, "
        f"覆盖 {len(score_matrix)} 张作品"
    )
    return sorted_pids, score_matrix, vision_log


async def vision_filter_multi_group(
    images: List[Dict],
    group_preferences: Dict[int, List[UserPreference]],
    target_count: int = 15,
) -> Tuple[Dict[int, List[int]], Dict[int, Dict[str, Any]]]:
    """
    跨群合并 vision 评分：多个群共享图片下载和 API 调用。

    Returns:
        ({group_id: [pid, ...]}, {group_id: vision_log})
    """
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

    logger.info(
        f"Vision 跨群评分: {len(group_preferences)} 个群, {len(flat_users)} 个用户, "
        f"{len(images)} 张候选图"
    )

    sorted_pids, score_matrix, vision_log = await vision_filter_images(images, flat_users)
    if not sorted_pids or not score_matrix:
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
        group_users = [
            user for user in all_users
            if user.get("user_idx") in allowed_indices
        ]
        logs[gid] = {
            **vision_log,
            "group_id": gid,
            "users": group_users,
            "scores": {str(pid): item for pid, item in group_scores.items()},
            "sorted_pids": group_sorted,
            "group_sorted_pids": results[gid],
        }
        logger.info(f"  群 {gid}: {len(group_sorted)} 张作品有评分 → 取前 {target_count} 张")

    return results, logs
