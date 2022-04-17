import asyncio

import datetime

import pytest
from hoshino.modules.pixiv.pixvirank.data_source import get_rank, RankPic, filter_rank, score_data, get_rankpic

def test_get_rank():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    rank = asyncio.run(get_rank(f'{yesterday}'))
    for r in rank:
        assert isinstance(r, RankPic)
    # with pytest.raises(Exception):
    #     tomorow = today + datetime.timedelta(days=1)
    #     rank = asyncio.run(get_rank(f'{tomorow}'))


def test_filter_rank():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    rank = asyncio.run(get_rank(f'{yesterday}'))
    pics = filter_rank(rank)
    pre = pics[0]
    for r in pics:
        for pids in score_data.last_three_days:
            assert r.pid not in pids
        assert r.score <= pre.score
        pre = r

def test_get_rankpic():
    p = asyncio.run(get_rankpic('97550456'))
    assert p.pid == 97550456
    assert p.author_id == 4460847

