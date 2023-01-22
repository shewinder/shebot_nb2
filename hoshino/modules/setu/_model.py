from typing import List, Optional, Any
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

class Yande(BaseModel):
    id: int
    tags: str
    created_at: int
    updated_at: int
    creator_id: int = None
    approver_id: int = None
    author: str
    change: int
    source: str
    score: int
    md5: str
    file_size: int
    file_ext: str
    file_url: str
    is_shown_in_index: bool
    preview_url: str
    preview_width: int
    preview_height: int
    actual_preview_width: int
    actual_preview_height: int
    sample_url: str
    sample_width: int
    sample_height: int
    sample_file_size: int
    jpeg_url: str
    jpeg_width: int
    jpeg_height: int
    jpeg_file_size: int
    rating: str
    is_rating_locked: bool
    has_children: bool
    parent_id: int = None
    status: str
    is_pending: bool
    width: int
    height: int
    is_held: bool
    frames_pending_string: str
    frames_pending: List[Any]
    frames_string: str
    frames: List[Any]
    is_note_locked: bool
    last_noted_at: int
    last_commented_at: int

def yande_to_setu(yande: Yande) -> Setu:
    st = Setu()
    st.tags = yande.tags
    st.r18 = 'uncensored' in yande.tags
    st.url = yande.sample_url.replace('files.yande.re', 'files.shewinder.win')
    # st.url = yande.jpeg_url.replace('files.yande.re', 'files.shewinder.win')
    # st.url = yande.file_url.replace('files.yande.re', 'files.shewinder.win')
    return st

    
