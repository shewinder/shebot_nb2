from peewee import *
from datetime import datetime

_db = SqliteDatabase(None)

class BaseModel(Model):
    class Meta:
        database = _db

class User(BaseModel):
    qqid = BigIntegerField(primary_key=True)
    name = TextField()

class Practice(BaseModel):
    id_ = BigIntegerField(primary_key=True)
    #type = TextField(null=True) # 训练类型,骑行跑步,可以为空
    publish_id = BigIntegerField() # 发布者QQ
    publish_time = DateTimeField(default=datetime.now) # 发布时间
    title = TextField() # 标题
    content = TextField()
    status = IntegerField(default=0) # 训练状态: 0报名阶段, 1截至报名阶段 2签到阶段 10结束
    token = TextField(null=True)

class SignUpRecord(BaseModel):
    uid = BigIntegerField()
    practice_id = BigIntegerField() # 哪次训练
    name = TextField()
    signup_time = DateTimeField(default=datetime.now) #报名时间
    class Meta:
        primary_key = CompositeKey('uid', 'practice_id')

class CheckInRecord(BaseModel):
    uid = BigIntegerField()
    practice_id = BigIntegerField() # 哪次训练
    name = TextField()
    checkin_time = DateTimeField(default=datetime.now) #签到时间
    class Meta:
        primary_key = CompositeKey('uid', 'practice_id')

class PigoenRecord(BaseModel):
    uid = BigIntegerField()
    practice_id = BigIntegerField() # 哪次训练
    name = TextField()
    remark = TextField(null=True)
    class Meta:
        primary_key = CompositeKey('uid', 'practice_id')

def init(sqlite_filename):
    _db.init(
        database=sqlite_filename,
        #pragmas={
        #    'journal_mode': 'wal',
        #    'cache_size': -1024 * 64,
        #},
    )

    if not User.table_exists():
        User.create_table()
    if not Practice.table_exists():
        Practice.create_table()
    if not SignUpRecord.table_exists():
        SignUpRecord.create_table()
    if not CheckInRecord.table_exists():
        CheckInRecord.create_table()
    if not PigoenRecord.table_exists():
        PigoenRecord.create_table()

if __name__ == '__main__':
    db_file = 'data/db/expedition.db'
    init(db_file)
    User.get_or_create(qqid=2813349544, name='罗振旭')
    User.get_or_create(qqid=1484279033, name='韩老头')
    User.get_or_create(qqid=925845546, name='俞洪锐')