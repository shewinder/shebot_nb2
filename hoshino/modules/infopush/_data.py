import os

import peewee as pw
from hoshino import db_dir

db_path = db_dir.joinpath('infopush.db')
db = pw.SqliteDatabase(db_path)

class SubscribeRecord(pw.Model):
    url = pw.TextField()
    checker = pw.TextField()
    remark = pw.TextField(default="")
    date = pw.TextField(default="")
    creator = pw.TextField()
    group = pw.TextField()

    class Meta:
        database = db
        primary_key = pw.CompositeKey('url', 'creator', 'group')

def query_records():
    return SubscribeRecord.select()

if not os.path.exists(db_path):
    db.connect()
    db.create_tables([SubscribeRecord])
    db.close()

class ExistsException(Exception):
    pass

class NotFoundException(Exception):
    pass

class KeywordConflictException(Exception):
    pass