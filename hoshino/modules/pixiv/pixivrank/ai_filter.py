'''
Author: SheBot
Date: 2026-04-08
Description: AI 图片筛选 - 支持多用户分批次加权筛选
'''
import json
from typing import List, Dict, Optional, Tuple
import httpx
from hoshino import userdata_dir
from hoshino.log import logger


def read_user_preference(user_id: str) -> str:
    """读取用户画像文件"""
    path = userdata_dir.joinpath(f"aichat/preferences/{user_id}.md")
    if path.exists():
        content = path.read_text(encoding='utf-8')
        logger.debug(f"读取画像文件成功: {path}，长度 {len(content)}")
        return content
    logger.debug(f"画像文件不存在: {path}")
    return ""


async def _call_ai_filter(
    preference: str,
    images: List[Dict],
    api_base: str,
    api_key: str,
    model: str,
    select_count: int,
) -> Optional[List[int]]:
    """单次 AI 筛选调用，返回选中的 PID 列表"""

    img_descriptions = []
    for i, img in enumerate(images, 1):
        tags_str = ", ".join(img.get("tags", [])[:10])
        img_descriptions.append(
            f"[{i}] PID:{img['pid']} | {img['title']} | 作者:{img['author']} | 标签:{tags_str}"
        )

    system_prompt = """你是一个图片推荐助手。根据用户的画像喜好，从候选图片中选择最符合的图片。
注意：必须返回图片的 PID（数字ID），不要返回序号。
只返回 JSON 格式，不要任何解释：
{
  "selected": [pid1, pid2, pid3, ...],
  "reason": "简要说明选择理由"
}"""

    user_prompt = f"""【用户画像】
{preference[:3000]}

【候选图片】（共{len(images)}张）
{chr(10).join(img_descriptions)}

请从中选择最符合用户喜好的 {select_count} 张图片。
重要：返回每个图片的 PID 数字（如 143198268），不是方括号里的序号！"""

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 500
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
        selected_pids_raw = result.get("selected", [])

        # 类型转换
        selected_pids = []
        for pid in selected_pids_raw:
            try:
                selected_pids.append(int(pid))
            except (ValueError, TypeError):
                logger.warning(f"AI 返回的 PID 无法转换为整数: {pid}")

        # 验证 PID 有效性
        valid_pids = {img["pid"] for img in images}
        filtered = [pid for pid in selected_pids if pid in valid_pids]

        invalid_pids = [pid for pid in selected_pids if pid not in valid_pids]
        if invalid_pids:
            logger.warning(f"AI 返回了无效 PID: {invalid_pids}")

        return filtered


async def ai_filter_images(
    user_id: str,
    images: List[Dict],
    api_base: str,
    api_key: str,
    model: str,
    select_count: int = 6
) -> Optional[List[int]]:
    """
    调用 AI 根据单个用户喜好筛选图片（兼容旧接口）
    """
    logger.info(f"开始 AI 筛选: user_id={user_id}, 候选图片={len(images)}张, 目标={select_count}张")

    preference = read_user_preference(user_id)
    if not preference:
        logger.info(f"用户 {user_id} 无画像文件，跳过 AI 筛选")
        return None

    if not api_key:
        logger.warning("AI API 密钥未配置，跳过 AI 筛选")
        return None

    logger.info(f"画像长度: {len(preference)} 字符，准备调用 AI")

    try:
        result = await _call_ai_filter(
            preference=preference,
            images=images,
            api_base=api_base,
            api_key=api_key,
            model=model,
            select_count=select_count,
        )
        logger.info(f"AI 筛选完成: 从 {len(images)} 张选中 {len(result)} 张")
        return result[:select_count] if result else None

    except httpx.HTTPStatusError as e:
        logger.error(f"AI API HTTP 错误: {e.response.status_code} - {e.response.text[:200]}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"AI 返回 JSON 解析失败: {e}")
        return None
    except Exception as e:
        logger.exception(f"AI 筛选失败: {e}")
        return None


async def ai_filter_images_multi_user(
    images: List[Dict],
    user_preferences: List[Tuple[str, bool]],
    api_base: str,
    api_key: str,
    model: str,
    select_count: int = 15,
    max_users: int = 8,
) -> Optional[List[int]]:
    """
    为多个用户分别调用 AI 筛选，每人配额制，给每个人一个机会。

    配额计算: 每人至少 3 张，超级用户额外 +2 张。
    合并去重后按"多人共同喜欢优先、有超级用户推荐优先"排序，
    超过 select_count 则截取，不足则由调用方补齐。

    Args:
        images: 候选图片列表
        user_preferences: [(preference_text, is_superuser), ...]
        api_base: AI API 地址
        api_key: AI API 密钥
        model: 模型名称
        select_count: 最终返回数量
        max_users: 最多处理多少个用户（避免 API 调用过多）

    Returns:
        排序后的 PID 列表，失败时返回 None
    """
    if not user_preferences:
        logger.info("无用户画像，跳过多用户 AI 筛选")
        return None

    if not api_key:
        logger.warning("AI API 密钥未配置，跳过 AI 筛选")
        return None

    # 限制用户数量
    user_preferences = user_preferences[:max_users]
    user_count = len(user_preferences)

    # 每人配额：均分，至少 3 张；超级用户额外 +2
    base_quota = max(3, select_count // user_count)
    logger.info(
        f"开始多用户 AI 筛选: 用户={user_count}人, 基础配额={base_quota}张, "
        f"候选={len(images)}张, 最终目标={select_count}张"
    )

    # 记录每张图被谁推荐: pid -> [(user_idx, is_superuser), ...]
    vote_details: Dict[int, List[Tuple[int, bool]]] = {}

    for i, (preference, is_su) in enumerate(user_preferences):
        if not preference:
            continue

        quota = min(base_quota + (2 if is_su else 0), len(images))
        user_label = "超级用户" if is_su else "普通用户"
        logger.info(f"第 {i+1}/{user_count} 次 AI 调用 ({user_label}, 配额 {quota} 张), 画像长度 {len(preference)}")

        try:
            selected = await _call_ai_filter(
                preference=preference,
                images=images,
                api_base=api_base,
                api_key=api_key,
                model=model,
                select_count=quota,
            )
            if selected:
                for pid in selected:
                    if pid not in vote_details:
                        vote_details[pid] = []
                    vote_details[pid].append((i, is_su))
                logger.info(f"  选中 {len(selected)} 张")
        except Exception as e:
            logger.warning(f"  该用户 AI 筛选失败: {e}")
            continue

    if not vote_details:
        logger.info("所有用户 AI 筛选均未返回结果")
        return None

    # 排序规则：
    # 1. 被推荐次数越多越优先（多人共识）
    # 2. 有超级用户推荐的优先
    # 3. 首次被超级用户推荐的优先（用 user_idx 最小值判断）
    def sort_key(pid: int):
        details = vote_details[pid]
        count = len(details)
        has_su = any(is_su for _, is_su in details)
        first_su_idx = min((idx for idx, is_su in details if is_su), default=999)
        return (count, has_su, -first_su_idx)

    sorted_pids = sorted(vote_details.keys(), key=sort_key, reverse=True)
    logger.info(
        f"多用户 AI 筛选完成: 汇总 {len(vote_details)} 张不同作品, "
        f"取前 {select_count} 张"
    )
    return sorted_pids[:select_count]
