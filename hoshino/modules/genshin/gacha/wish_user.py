from .model import GachaRecord

class WishUser:
    def __init__(self, uid, gacha_type):
        self.uid = uid
        self.gacha_type = gacha_type
        last_rank5: GachaRecord = GachaRecord.select()\
        .where(GachaRecord.uid == uid, GachaRecord.gacha_type == gacha_type, GachaRecord.rank == 5)\
        .order_by(GachaRecord.id.desc()).first()
        self.count_5 = last_rank5.chara_count5 if last_rank5 else 0
        last_rank4: GachaRecord = GachaRecord.select()\
        .where(GachaRecord.uid == uid, GachaRecord.gacha_type == gacha_type, GachaRecord.rank == 4)\
        .order_by(GachaRecord.id.desc()).first()
        self.count_4 = last_rank4.chara_count4 if last_rank4 else 0
        
