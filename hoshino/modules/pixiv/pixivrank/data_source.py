from dataclasses import dataclass
from random import choices
from typing import Dict, List

import aiohttp

from .._model import Illust, PixivIllust
from .score import score_data


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


async def filter_rank(pics: List[RankPic]) -> List[RankPic]:
    def sum_score(pic: RankPic):
        return sum(
            score_data.tag_scores.get(tag, 0) for tag in pic.tags
        ) + score_data.author_scores.get(str(pic.author_id), 0)

    def not_sent_in_3_days(pic: RankPic):
        for i in score_data.last_three_days:
            if pic.pid in i:
                return False
        return True

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
    
    # 如果未满15张，继续自动挑选流程
    pics = list(filter(not_sent_in_3_days, pics))
    for pic in pics:
        pic.score = sum_score(pic)
    pics = list(filter(lambda x: x.score >= 0, pics))
    
    # 从pics中移除已经选择的图片（避免重复）
    selected_pids_set = {p.pid for p in selected_pics}
    pics = [p for p in pics if p.pid not in selected_pids_set]
    
    # 继续选择直到15张
    remaining = 15 - len(selected_pics)
    for _ in range(remaining):
        try:
            if len(pics) == 0:
                break
            sidx = choices(range(len(pics)), weights=[x.score + 1 for x in pics], k=1)[0]
            selected_pics.append(pics.pop(sidx))
        except:
            continue
    return selected_pics


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
