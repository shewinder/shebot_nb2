from itertools import count
import peewee as pw
import os
from hoshino import db_dir


db_path = os.path.join(db_dir, 'genshin-gacha.db')
db = pw.SqliteDatabase(db_path)


class GachaRecord(pw.Model):
    id = pw.BigIntegerField(primary_key=True)
    uid = pw.BigIntegerField()
    gacha_type = pw.IntegerField()
    rank = pw.IntegerField()
    name = pw.CharField()
    is_up = pw.BooleanField()
    ctime = pw.DateTimeField()
    chara_count5 = pw.IntegerField()
    chara_count4 = pw.IntegerField()
    weapon_count5 = pw.IntegerField()
    weapon_count4 = pw.IntegerField()

    class Meta:
        database = db

if not os.path.exists(db_path):
    db.connect()
    GachaRecord.create_table()
    db.close()