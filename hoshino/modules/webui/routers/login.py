from fastapi import APIRouter, Response
from pydantic import BaseModel
from nonebot import get_driver

from .._util import create_token

router = APIRouter()

# 从 .env 配置读取密码
driver = get_driver()
WEB_PASSWORD = getattr(driver.config, 'web_password', 'shebot')

class LoginForm(BaseModel):
    password: str

@router.post('/login')
async def handle_login(form: LoginForm):
    if form.password != WEB_PASSWORD:
        return Response(status_code=401, content='密码错误')
    token = create_token('admin')
    return {'status': 200, 'data': token}