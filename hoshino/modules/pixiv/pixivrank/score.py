from typing import Dict, List
from hoshino import userdata_dir
from pydantic import BaseModel

class ScoreData(BaseModel):
    tag_scores: Dict[str, int] = {}
    author_scores: Dict[str, int] = {}
    last_three_days: List[List[int]] = [[]]

d = userdata_dir.joinpath('pixiv')
if not d.exists():
    d.mkdir()
p = d.joinpath('pixiv_score.json')
if not p.exists():
    p.touch()
    p.write_text(ScoreData().model_dump_json())


score_data = ScoreData.model_validate_json(p.read_text())

save_score_data = lambda: p.write_text(score_data.model_dump_json())
load_score_data = lambda: ScoreData.model_validate_json(p.read_text())
    