import os

import peewee as pw
from pathlib import Path
from hoshino.typing import Optional
from hoshino import db_dir
from peewee import *

db_path = os.path.join(db_dir, 'aria2.db')
db = SqliteDatabase(db_path)

class Aria2sql(pw.Model):
    mid = BigIntegerField()
    uid = BigIntegerField()
    gid = BigIntegerField()
    sid = BigIntegerField()
    typeid = TextField()
    class Meta:
        database = db

if not os.path.exists(db_path):
    if not Aria2sql.table_exists():
        Aria2sql.create_table()

async def write_mission(mid: str, uid: int, gid: Optional[int] = 0, sid: Optional[int] = 310080030, typeid: str = 'HTTP'):
    result = Aria2sql.get_or_none(Aria2sql.mid == mid)
    if result is None:
        Aria2sql.insert(
            mid=mid,
            uid=uid,
            gid=gid,
            sid=sid,
            typeid=typeid
        ).execute()
    else:
        Aria2sql.replace(
            mid=mid,
            uid=uid,
            gid=gid,
            sid=sid,
            typeid=typeid
        ).execute()
    return


async def del_mission(mid):
    result = Aria2sql.get_or_none(Aria2sql.mid == mid)
    if result is None:
        return
    else:
        result.delete_instance()
    return


async def load_mission(mid):
    result = Aria2sql.get_or_none(Aria2sql.mid == mid)
    if result is None:
        return None, None, None, None
    else:
        uid = result.uid
        gid = result.gid
        sid = result.sid
        typeid = result.typeid
    return uid, gid, sid, typeid


def trans_speed(num):
    int_num = int(num)
    if int_num <= 1024:
        return str(int_num) + "b/s"
    else:
        int_num = int_num / 1024
        if int_num <= 1024:
            return str(int_num)[0:5] + "kb/s"
        else:
            int_num = int_num / 1024
            return str(int_num)[0:5] + "mb/s"
