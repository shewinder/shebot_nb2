from dataclasses import dataclass
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

def to_rankpic(illust: Illust):
    pic = PixivIllust(illust)
    tags = [tag.name for tag in pic.tags]
    return RankPic(
        pic.id,
        pic.urls[0],
        tags,
        0,
        pic.page_count,
        pic.user.name,
        pic.user.id,
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
                    res.append(to_rankpic(Illust(**data)))
                return res


def filter_rank(pics: List[RankPic]) -> List[RankPic]:
    def sum_score(pic: RankPic):
        return sum(
            score_data.tag_scores.get(tag, 0) for tag in pic.tags
        ) + score_data.author_scores.get(str(pic.author_id), 0)

    def already_sent_in_3_days(pic: RankPic):
        for i in score_data.last_three_days:
            if pic.pid in i:
                return True
        return False

    filter(not already_sent_in_3_days, pics)
    for pic in pics:
        pic.score = sum_score(pic)

    pics.sort(key=lambda x: x.score, reverse=True)
    return pics[0:15]


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
