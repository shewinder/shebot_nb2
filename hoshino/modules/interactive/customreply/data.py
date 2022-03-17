import os

import peewee as pw
from hoshino import userdata_dir

plug_dir = userdata_dir.joinpath('customreply')
if not plug_dir.exists():
    plug_dir.mkdir()
db_path = plug_dir.joinpath('customreply.db')
db = pw.SqliteDatabase(db_path)

class CustomReply(pw.Model):
    word = pw.TextField()
    reply = pw.TextField()
    matcher = pw.TextField()

    class Meta:
        database = db

if not os.path.exists(db_path):
    db.connect()
    db.create_tables([CustomReply])
    db.close()

class ExistsException(Exception):
    pass

class NotFoundException(Exception):
    pass

class KeywordConflictException(Exception):
    pass