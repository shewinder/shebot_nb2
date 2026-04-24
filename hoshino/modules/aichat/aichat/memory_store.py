"""用户记忆持久化存储模块"""
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel
from loguru import logger

from hoshino import userdata_dir

aichat_data_dir = Path(userdata_dir).joinpath('aichat')
SUMMARIES_DIR = aichat_data_dir / 'memories' / 'summaries'
FACTS_DIR = aichat_data_dir / 'memories' / 'facts'


class SessionSummary(BaseModel):
    """会话摘要"""
    session_id: str
    summary: str
    active_skills: List[str]
    has_pending_tasks: bool
    timestamp: datetime
    message_count: int


class UserFact(BaseModel):
    """用户事实"""
    key: str
    value: str
    confidence: float
    updated_at: datetime
    source: str


def _ensure_dirs() -> None:
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    FACTS_DIR.mkdir(parents=True, exist_ok=True)


def _iso_fields() -> List[str]:
    return ['timestamp', 'updated_at']


def _summary_file(user_id: int) -> Path:
    _ensure_dirs()
    return SUMMARIES_DIR / f"{user_id}.json"


def _facts_file(user_id: int) -> Path:
    _ensure_dirs()
    return FACTS_DIR / f"{user_id}.json"


def load_summaries(user_id: int) -> List[SessionSummary]:
    """加载用户的会话摘要列表"""
    file_path = _summary_file(user_id)
    if not file_path.exists():
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        summaries = []
        for item in data.get('summaries', []):
            for field in _iso_fields():
                if item.get(field):
                    item[field] = datetime.fromisoformat(item[field])
            summaries.append(SessionSummary(**item))
        return summaries
    except Exception as e:
        logger.warning(f"加载用户 {user_id} 的摘要失败: {e}")
        return []


def save_summaries(user_id: int, summaries: List[SessionSummary]) -> None:
    """保存用户的会话摘要列表"""
    file_path = _summary_file(user_id)
    try:
        data = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "summaries": []
        }
        for s in summaries:
            item = s.model_dump()
            for field in _iso_fields():
                if item.get(field):
                    item[field] = item[field].isoformat()
            data["summaries"].append(item)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception(f"保存用户 {user_id} 的摘要失败: {e}")


def load_facts(user_id: int) -> List[UserFact]:
    """加载用户的事实列表"""
    file_path = _facts_file(user_id)
    if not file_path.exists():
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        facts = []
        for item in data.get('facts', []):
            for field in _iso_fields():
                if item.get(field):
                    item[field] = datetime.fromisoformat(item[field])
            facts.append(UserFact(**item))
        return facts
    except Exception as e:
        logger.warning(f"加载用户 {user_id} 的事实失败: {e}")
        return []


def save_facts(user_id: int, facts: List[UserFact]) -> None:
    """保存用户的事实列表"""
    file_path = _facts_file(user_id)
    try:
        data = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "facts": []
        }
        for f in facts:
            item = f.model_dump()
            for field in _iso_fields():
                if item.get(field):
                    item[field] = item[field].isoformat()
            data["facts"].append(item)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception(f"保存用户 {user_id} 的事实失败: {e}")
