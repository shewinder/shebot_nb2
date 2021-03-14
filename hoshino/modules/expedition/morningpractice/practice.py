from typing import Union, List
from .data import Practice, SignUpRecord
from loguru import logger

class PracticeManager:
    def get_current_practice() -> Union[Practice, None]:
        try:
            prts = Practice.select().where((Practice.status!=10)) # 获取所有未完成的早训
            return prts if prts else None
        except Exception as e:
            logger.exception(e)
            return None

    def get_practice_by_status(status: int) -> Union[Practice, None]:
        try:
            prts = Practice.select().where((Practice.status == status)) # 获取所有未完成的早训
            return prts if prts else None
        except Exception as e:
            logger.exception(e)
            return None

            
class SignUpRecordManager:
    def get_signup_records(practice_id) -> List[SignUpRecord]:
        try:
            recs = SignUpRecord.select().where(SignUpRecord.practice_id == practice_id)
            return recs
        except Exception as e:
            logger.exception(e)
            return None
    
    def is_signed(qqid, practice_id):
        try:
            rec = SignUpRecord.get_or_none(uid=qqid, practice_id=practice_id)
        except Exception as e:
            logger.exception(e)
        return True if rec else False
    
    def del_signup_record(qqid, practice_id):
        try:
            rec: SignUpRecord = SignUpRecord.get_or_none(uid=qqid, practice_id=practice_id)
            if rec:
                return rec.delete_instance()
            else:
                return 0
        except Exception as e:
            logger.exception(e)      


