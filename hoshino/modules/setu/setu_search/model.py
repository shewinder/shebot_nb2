from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, validator

class Setu(BaseModel):
    pid: int
    p: int
    uid: int
    title: str
    author: str
    r18: bool
    width: int
    height: int
    tags: List[str]
    ext: str
    upload_date: datetime
    url: str

    @validator('tags', pre=True)
    def tag_str2list(cls, v):
        if isinstance(v, str):
            return v.split(',')
        return v
    
