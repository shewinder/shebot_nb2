from dataclasses import dataclass
from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel


class ImageUrls(BaseModel):
    large: Optional[str] = None
    medium: Optional[str] = None
    square_medium: Optional[str] = None



class MetaSinglePage(BaseModel):
    original_image_url: Optional[str] = None


class Tag(BaseModel):
    translated_name: None
    name: Optional[str] = None



class ProfileImageUrls(BaseModel):
    medium: Optional[str] = None


class User(BaseModel):
    account: Optional[str] = None
    id: Optional[int] = None
    is_followed: Optional[bool] = None
    name: Optional[str] = None
    profile_image_urls: Optional[ProfileImageUrls] = None



class Illust(BaseModel):
    series: None
    caption: Optional[str] = None
    comment_access_control: Optional[int] = None
    create_date: Optional[datetime] = None
    height: Optional[int] = None
    id: Optional[int] = None
    image_urls: Optional[ImageUrls] = None
    is_bookmarked: Optional[bool] = None
    is_muted: Optional[bool] = None
    meta_pages: Optional[List[Any]] = None
    meta_single_page: Optional[MetaSinglePage] = None
    page_count: Optional[int] = None
    restrict: Optional[int] = None
    sanity_level: Optional[int] = None
    tags: Optional[List[Tag]] = None
    title: Optional[str] = None
    tools: Optional[List[Any]] = None
    total_bookmarks: Optional[int] = None
    total_comments: Optional[int] = None
    total_view: Optional[int] = None
    type: Optional[str] = None
    user: Optional[User] = None
    visible: Optional[bool] = None
    width: Optional[int] = None
    x_restrict: Optional[int] = None
