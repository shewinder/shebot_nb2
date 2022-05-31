import os

import peewee as pw
from hoshino import userdata_dir

plug_dir = userdata_dir.joinpath('web')
if not plug_dir.exists():
    plug_dir.mkdir()
db_path = plug_dir.joinpath('user.db')
db = pw.SqliteDatabase(db_path)

class User(pw.Model):
    uid = pw.TextField()
    group_id = pw.TextField()
    name = pw.TextField()
    password = pw.TextField()
    avatar = pw.TextField(null=True)
    group_id = pw.TextField()
    group_name = pw.TextField(null=True)

    class Meta:
        database = db
        primary_key = pw.CompositeKey('uid', 'group_id')

if not os.path.exists(db_path):
    db.connect()
    db.create_tables([User])
    db.close()

class ExistsException(Exception):
    pass

class NotFoundException(Exception):
    pass

class KeywordConflictException(Exception):
    pass