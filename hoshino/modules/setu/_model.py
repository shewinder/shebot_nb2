from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, validator

class Setu(BaseModel):
    pid: int = 0
    p: int = 0
    uid: int = 0
    title: str = ''
    author: str = ''
    r18: bool = False
    width: int = 0
    height: int = 0
    tags: List[str] = []   
    ext: str = ''
    upload_date: datetime = datetime.now()
    url: str = ''

    @validator('tags', pre=True)
    def tag_str2list(cls, v):
        if isinstance(v, str):
            return v.split(',')
        return v
    
