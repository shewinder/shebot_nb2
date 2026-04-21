from dataclasses import dataclass
from random import choices
from typing import Dict, List, Optional, Tuple

import aiohttp
from hoshino import userdata_dir
from hoshino.log import logger

from .._model import Illust, PixivIllust
from .score import score_data
from .ai_filter import ai_filter_images, ai_filter_images_multi_user
from .config import Config


conf = Config.get_instance("pixivrank")


@dataclass
class RankPic:
    pid: int
    url: str
    tags: List[str]
    score: int
    page_count: int
    author: str
    author_id: int
    urls: List[str]
    title: str = ""

def to_rankpic(illust: Illust):
    pic = PixivIllust(**illust.dict())
    tags = [tag.name for tag in pic.tags if tag.name]
    tags.extend([tag.translated_name for tag in pic.tags if tag.translated_name])
    return RankPic(
        pic.id,
        pic.urls[0],
        tags,
        0,
        pic.page_count,
        pic.user.name,
        pic.user.id,
        pic.urls,
        pic.title or "",
    )


async def get_rank(date: str, mode: str = "day") -> List[RankPic]:
    url = "https://api.shewinder.win/pixiv/rank"
    params = {"date": date, "mode": mode, "num": 60}
    res = []
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                for d in data:
                    if d["type"] != "illust":
                        continue
                    res.append(to_rankpic(Illust(**d)))
                return res
            else:
                raise Exception(f'status {resp.status}')


async def get_selected_images() -> List[int]:
    """获取手动选择的图片ID列表"""
    url = "https://rsshub.shewinder.win/api/get-selected-images"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("selected_images", [])
    except Exception:
        pass
    return []


def sum_score(pic: RankPic) -> int:
    """计算图片的综合评分"""
    return sum(
        score_data.tag_scores.get(tag, 0) for tag in pic.tags
    ) + score_data.author_scores.get(str(pic.author_id), 0)


def not_sent_in_3_days(pic: RankPic) -> bool:
    """检查图片是否在最近3天内发送过"""
    for i in score_data.last_three_days:
        if pic.pid in i:
            return False
    return True


def weighted_select(pics: List[RankPic], count: int) -> List[RankPic]:
    """
    加权随机选择指定数量的图片
    
    Args:
        pics: 候选图片列表（会被修改，注意传入副本）
        count: 需要选择的数量
    
    Returns:
        选中的图片列表
    """
    selected = []
    for _ in range(count):
        try:
            if len(pics) == 0:
                break
            sidx = choices(range(len(pics)), weights=[x.score + 1 for x in pics], k=1)[0]
            selected.append(pics.pop(sidx))
        except Exception:
            continue
    return selected


async def filter_rank(pics: List[RankPic], target_count: int = 15) -> List[RankPic]:
    """原有的基础过滤逻辑（基于评分和历史记录）"""
    # 获取手动选择的图片ID列表
    selected_pids = await get_selected_images()
    selected_pics = []
    pics_dict = {pic.pid: pic for pic in pics}
    
    # 优先添加手动选择的图片
    for pid in selected_pids:
        if pid in pics_dict:
            # 从排行榜中找到的图片
            pic = pics_dict[pid]
            if not_sent_in_3_days(pic):
                pic.score = sum_score(pic)
                if pic.score >= 0:
                    selected_pics.append(pic)
                    # 从pics中移除，避免重复选择
                    pics = [p for p in pics if p.pid != pid]
        else:
            # 不在排行榜中，尝试通过API获取
            try:
                pic = await get_rankpic(str(pid))
                if pic and not_sent_in_3_days(pic):
                    pic.score = sum_score(pic)
                    if pic.score >= 0:
                        selected_pics.append(pic)
            except Exception:
                pass
    
    # 如果未满 target_count 张，继续自动挑选流程
    pics = list(filter(not_sent_in_3_days, pics))
    for pic in pics:
        pic.score = sum_score(pic)
    pics = list(filter(lambda x: x.score >= 0, pics))
    
    # 从pics中移除已经选择的图片（避免重复）
    selected_pids_set = {p.pid for p in selected_pics}
    pics = [p for p in pics if p.pid not in selected_pids_set]
    
    # 继续选择直到 target_count 张
    remaining = target_count - len(selected_pics)
    selected_pics.extend(weighted_select(pics, remaining))
    return selected_pics


async def read_group_preferences(group_id: int, bot) -> List[Tuple[str, bool]]:
    """
    读取群内有画像的成员画像列表

    Args:
        group_id: 群号
        bot: Bot 实例，用于获取群成员列表

    Returns:
        List[Tuple[preference_text, is_superuser]]
        超级用户排在前面
    """
    from hoshino import hsn_config

    superusers = {str(su) for su in getattr(hsn_config, 'superusers', set())}

    # 获取群成员列表
    member_ids: set = set()
    try:
        members = await bot.get_group_member_list(group_id=group_id)
        for m in members:
            uid = m.get('user_id') or m.get('qq')
            if uid is not None:
                member_ids.add(str(uid))
        logger.info(f"群 {group_id} 成员数: {len(member_ids)}")
    except Exception as e:
        logger.warning(f"获取群 {group_id} 成员列表失败: {e}")
        return []

    # 扫描画像目录，找出群成员中有画像的
    pref_dir = userdata_dir.joinpath('aichat/preferences')
    if not pref_dir.exists():
        logger.info(f"画像目录不存在: {pref_dir}")
        return []

    result = []
    for f in pref_dir.iterdir():
        if not f.is_file() or f.suffix != '.md':
            continue
        user_id = f.stem
        if user_id not in member_ids:
            continue
        try:
            content = f.read_text(encoding='utf-8').strip()
            if content:
                is_su = user_id in superusers
                result.append((content, is_su))
        except Exception as e:
            logger.warning(f"读取画像文件失败 {f}: {e}")

    # 超级用户排前面
    result.sort(key=lambda x: (not x[1], x[0][:20]))
    logger.info(f"群 {group_id} 找到 {len(result)} 个有画像的成员（含超级用户 {sum(1 for _, s in result if s)} 个）")
    return result


async def filter_rank_ai(
    pics: List[RankPic],
    group_id: int,
    bot=None,
    target_count: int = 15
) -> List[RankPic]:
    """
    智能图片筛选：优先 AI 根据群内所有用户画像筛选，剩余用原逻辑补齐
    
    Args:
        pics: 原始图片列表
        group_id: 群号，用于读取该群成员画像
        bot: Bot 实例，获取群成员列表需要
        target_count: 目标返回数量（默认15张）
    
    Returns:
        筛选后的 RankPic 列表
    """
    # 检查 AI 筛选是否启用
    if not conf.ai_filter_enabled:
        return await filter_rank(pics, target_count)
    
    # 基础过滤：排除已发送、计算评分
    candidates = list(filter(not_sent_in_3_days, pics))
    after_dedup = len(candidates)
    for pic in candidates:
        pic.score = sum_score(pic)
    candidates = list(filter(lambda x: x.score >= 0, candidates))
    after_score = len(candidates)
    logger.info(
        f"群 {group_id} 基础过滤: 原始 {len(pics)} 张 -> "
        f"去重后 {after_dedup} 张 -> 评分过滤后 {after_score} 张"
    )
    
    # 准备 AI 筛选所需数据
    images = [
        {
            "pid": p.pid,
            "title": p.title,
            "author": p.author,
            "tags": p.tags
        }
        for p in candidates
    ]
    
    result = []
    remaining_candidates = candidates.copy()
    
    # 尝试读取群内多用户画像并调用 AI 筛选
    if bot is not None and conf.ai_api_key:
        user_preferences = await read_group_preferences(group_id, bot)
        if user_preferences:
            ai_count = min(conf.ai_select_count, target_count)
            selected_pids = await ai_filter_images_multi_user(
                images=images,
                user_preferences=user_preferences,
                api_base=conf.ai_api_base,
                api_key=conf.ai_api_key,
                model=conf.ai_model,
                select_count=ai_count,
            )
            if selected_pids:
                pid_map = {p.pid: p for p in candidates}
                for pid in selected_pids:
                    if pid in pid_map:
                        result.append(pid_map[pid])
                        remaining_candidates = [p for p in remaining_candidates if p.pid != pid]
                logger.info(f"群 {group_id} AI 多用户筛选选中 {len(result)} 张")
    
    # 如果 AI 未选中或数量不足，用原逻辑补齐
    current_count = len(result)
    if current_count < target_count and len(remaining_candidates) > 0:
        need_count = target_count - current_count
        additional = weighted_select(remaining_candidates, need_count)
        result.extend(additional)
        logger.info(f"群 {group_id} 原逻辑补齐 {len(additional)} 张，共 {len(result)} 张")
    
    return result


async def get_rankpic(pid: str) -> RankPic:
    url = "https://api.shewinder.win/pixiv/illust_detail"
    params = {"illust_id": pid}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                return to_rankpic(Illust(**data))
            else:
                return None
