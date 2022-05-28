import datetime
import time

import jwt
from jwt import ExpiredSignatureError
from pydantic import BaseModel
from loguru import logger

_secret = 'asafasfsadfeghgiohnjgjingbjndq'

def check_auth(token) -> bool:
    try:
        dic = jwt.decode(token, _secret, algorithms='HS256')
        return True
    except ExpiredSignatureError:
        logger.info('signature expired')
    except Exception as e:
        logger.exception(e)

def create_token(username) -> str:
    dic = {
        'username': username,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=3)
    }
    token = jwt.encode(dic, _secret, algorithm='HS256')
    return token
