import asyncio

import datetime
from hoshino.modules.pixiv.pixvirank.data_source import get_rank, RankPic

def test_get_rank():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    rank = asyncio.run(get_rank(f'{yesterday}'))
    for r in rank:
        assert isinstance(r, RankPic)
    # rank = asyncio.run(get_rank(f'{today}'))
    # assert len(rank) > 0