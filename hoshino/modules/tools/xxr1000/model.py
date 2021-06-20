import os

import peewee as pw

from hoshino import db_dir

db_path = os.path.join(db_dir, '1000（单表）.db3')
db = pw.SqliteDatabase(db_path)


class Quest(pw.Model):
    ID = pw.IntegerField()
    Question = pw.TextField()
    OptionA = pw.TextField()
    OptionB = pw.TextField()
    OptionC = pw.TextField()
    OptionD = pw.TextField()
    Answer = pw.CharField()
    Catalog = pw.TextField()
    class Meta:
        database = db
        table_name = '题目'

if not os.path.exists(db_path):
    raise FileNotFoundError('no database')
