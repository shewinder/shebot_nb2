from loguru import logger
from .data import User
from .exception import UserError

class UserManager:
    def get_name_by_qqid(qqid):
        try:
            user = User.get_or_none(qqid=qqid)
        except Exception as e:
            logger.exception(e)
        if user is None:
            raise UserError('不存在该用户')
        return user.name


    