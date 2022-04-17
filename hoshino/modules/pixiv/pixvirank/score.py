from typing import Dict, List
from hoshino.util.persist import Persistent
from hoshino import userdata_dir

class ScoreData(Persistent):
    tag_scores: Dict[str, int] = {}
    author_scores: Dict[str, int] = {}
    last_three_days: List[List[int]] = [[]]

d = userdata_dir.joinpath('pixiv')
if not d.exists():
    d.mkdir()
p = d.joinpath('pixiv_score.json')
if not p.exists():
    p.touch()

score_data = ScoreData(p)
    