from fastapi import APIRouter
from pydantic import BaseModel

from hoshino.modules.web.util.util import create_token

router = APIRouter()

class User(BaseModel):
    username: str
    password: str
@router.post('/login')
async def handle_login(user: User):
    if user.password == '426850':
        token = create_token('shebot')
        return {'status': 200, 'data': token}
    else:
        return {'status': 401, 'data': 'wrong password'}