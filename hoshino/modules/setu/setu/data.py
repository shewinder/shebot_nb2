import peewee as pw
import os
from hoshino import db_dir

db_path = os.path.join(db_dir, 'setu.db')
db = pw.SqliteDatabase(db_path)


class Setu(pw.Model):
    pid = pw.BigIntegerField()
    author = pw.TextField()
    title = pw.TextField()
    url = pw.TextField(unique=True)
    r18 = pw.IntegerField()
    tags = pw.TextField()
    class Meta:
        database = db

if not os.path.exists(db_path):
    if not Setu.table_exists():
        Setu.create_table()


