import os
import time
from datetime import datetime, timedelta

import peewee as pw
from hoshino import userdata_dir

plug_dir = userdata_dir.joinpath('groupmsglog')
if not plug_dir.exists():
    plug_dir.mkdir(parents=True)
db_path = plug_dir.joinpath('messages.db')
db = pw.SqliteDatabase(db_path, pragmas={'journal_mode': 'wal'})


class GroupMessage(pw.Model):
    id = pw.AutoField()
    message_id = pw.IntegerField(unique=True)
    group_id = pw.BigIntegerField(index=True)
    user_id = pw.BigIntegerField(index=True)
    nickname = pw.CharField(max_length=255, default='')
    card = pw.CharField(max_length=255, default='')
    content = pw.TextField(default='')
    raw_message = pw.TextField(default='')
    message_type = pw.CharField(max_length=64, default='')
    seq = pw.IntegerField(null=True)
    time = pw.IntegerField(default=0)
    recorded_at = pw.DateTimeField(constraints=[pw.SQL('DEFAULT CURRENT_TIMESTAMP')])

    class Meta:
        database = db
        indexes = (
            (('group_id', 'time'), False),
            (('user_id', 'time'), False),
            (('group_id', 'user_id'), False),
        )


if not os.path.exists(db_path):
    db.connect()
    db.create_tables([GroupMessage])
    db.close()


def _connect():
    if db.is_closed():
        db.connect()


def cleanup_old_messages(retention_days: int) -> int:
    """删除超过保留天数的消息，返回删除条数"""
    if retention_days <= 0:
        return 0
    _connect()
    cutoff = int((datetime.now() - timedelta(days=retention_days)).timestamp())
    deleted = GroupMessage.delete().where(GroupMessage.time < cutoff).execute()
    db.close()
    return deleted


def get_group_messages(
    group_id: int,
    start_time: int = None,
    end_time: int = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """查询群消息，用于总结或上下文"""
    _connect()
    query = GroupMessage.select().where(GroupMessage.group_id == group_id)
    if start_time:
        query = query.where(GroupMessage.time >= start_time)
    if end_time:
        query = query.where(GroupMessage.time < end_time)
    query = query.order_by(GroupMessage.time.desc()).offset(offset).limit(limit)
    result = [_msg_to_dict(m) for m in query]
    db.close()
    return result


def search_messages(
    group_id: int,
    user_id: int = None,
    keyword: str = None,
    start_time: int = None,
    end_time: int = None,
    limit: int = 50,
) -> list[dict]:
    """搜群消息，支持用户/关键词/时间范围过滤"""
    _connect()
    query = GroupMessage.select().where(GroupMessage.group_id == group_id)
    if user_id:
        query = query.where(GroupMessage.user_id == user_id)
    if keyword:
        query = query.where(GroupMessage.content.contains(keyword))
    if start_time:
        query = query.where(GroupMessage.time >= start_time)
    if end_time:
        query = query.where(GroupMessage.time < end_time)
    query = query.order_by(GroupMessage.time.asc()).limit(limit)
    result = [_msg_to_dict(m) for m in query]
    db.close()
    return result


def get_user_messages(
    user_id: int,
    group_id: int = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """查询用户消息，用于用户画像"""
    _connect()
    query = GroupMessage.select().where(GroupMessage.user_id == user_id)
    if group_id:
        query = query.where(GroupMessage.group_id == group_id)
    query = query.order_by(GroupMessage.time.desc()).offset(offset).limit(limit)
    result = [_msg_to_dict(m) for m in query]
    db.close()
    return result


def get_recent_messages(group_id: int, minutes: int = 30) -> list[dict]:
    """获取最近 N 分钟的群消息"""
    _connect()
    since = int(time.time()) - minutes * 60
    query = (GroupMessage
             .select()
             .where(GroupMessage.group_id == group_id, GroupMessage.time >= since)
             .order_by(GroupMessage.time.asc()))
    result = [_msg_to_dict(m) for m in query]
    db.close()
    return result


def get_group_stats(group_id: int, days: int = 7) -> dict:
    """获取群统计信息"""
    _connect()
    since = int((datetime.now() - timedelta(days=days)).timestamp())
    base = GroupMessage.select().where(
        GroupMessage.group_id == group_id,
        GroupMessage.time >= since,
    )
    total = base.count()
    users = (base
             .select(GroupMessage.user_id, pw.fn.COUNT(GroupMessage.id).alias('c'))
             .group_by(GroupMessage.user_id)
             .order_by(pw.fn.COUNT(GroupMessage.id).desc()))
    top_users = [(u.user_id, u.c) for u in users.limit(20)]
    db.close()
    return {'total_messages': total, 'top_users': top_users, 'days': days}


def _msg_to_dict(m: GroupMessage) -> dict:
    return {
        'id': m.id,
        'message_id': m.message_id,
        'group_id': m.group_id,
        'user_id': m.user_id,
        'nickname': m.nickname,
        'card': m.card,
        'content': m.content,
        'raw_message': m.raw_message,
        'message_type': m.message_type,
        'seq': m.seq,
        'time': m.time,
        'recorded_at': m.recorded_at.isoformat() if m.recorded_at else None,
    }
