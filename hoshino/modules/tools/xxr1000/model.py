import peewee as pw

from hoshino import res_dir

db_path = res_dir.joinpath('db/1000（单表）.db3')
db = pw.SqliteDatabase(str(db_path))

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

if not db_path.exists():
    raise FileNotFoundError('no database')
