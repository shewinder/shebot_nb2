from fastapi import APIRouter, Response
from pydantic import BaseModel

from hoshino.modules.web._util import create_token
from .._user import User as UserModel

router = APIRouter()

class User(BaseModel):
    username: str
    password: str

@router.post('/login')
async def handle_login(user: User):
    # if user.password == '426850':
    #     token = create_token('shebot')
    #     return {'status': 200, 'data': token}
    # else:
    #     return {'status': 401, 'data': 'wrong password'}
    # 查询数据库
    user_model: UserModel = UserModel.get(UserModel.uid == user.username)
    if not user_model:
        return {'status': 404, 'data': '用户不存在'}
    if user_model.password != user.password:
        return Response(status_code=401, content='用户名或者密码错误')
    token = create_token(user.username)
    return {'status': 200, 'data': token}