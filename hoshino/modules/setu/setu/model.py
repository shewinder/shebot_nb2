from typing import List

from pydantic import BaseModel

class Setu(BaseModel):
    picbytes: bytes = None
    pid: int
    author: str
    title: str
    url: str
    r18: int # 0 non-r18, 1 r18, 2 mixed
    tags: List


