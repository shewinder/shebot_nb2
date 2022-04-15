import asyncio

import datetime
from hoshino.modules.pixiv.pixvirank.data_source import get_rank, RankPic, filter_rank, score_data, get_rankpic

def test_get_rank():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    rank = asyncio.run(get_rank(f'{yesterday}'))
    for r in rank:
        assert isinstance(r, RankPic)

def test_filter_rank():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=2)
    rank = asyncio.run(get_rank(f'{yesterday}'))
    pics = filter_rank(rank)
    for r in pics:
        for pids in score_data.last_three_days:
            assert r.pid not in pids

def test_get_rankpic():
    p = asyncio.run(get_rankpic('97550456'))
    assert p.pid == 97550456
    assert p.author_id == 4460847

