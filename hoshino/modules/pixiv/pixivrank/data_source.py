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


def filter_rank(pics: List[RankPic]) -> List[RankPic]:
    def sum_score(pic: RankPic):
        return sum(
            score_data.tag_scores.get(tag, 0) for tag in pic.tags
        ) + score_data.author_scores.get(str(pic.author_id), 0)

    def not_sent_in_3_days(pic: RankPic):
        for i in score_data.last_three_days:
            if pic.pid in i:
                return False
        return True

    pics = list(filter(not_sent_in_3_days, pics))
    for pic in pics:
        pic.score = sum_score(pic)
    pics = list(filter(lambda x: x.score >= 0, pics))
    selected_pics = []
    for _ in range(15):
        try:
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
