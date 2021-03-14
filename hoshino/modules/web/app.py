from logging import log
from typing import Callable
import nonebot
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request, Response
from loguru import logger

from hoshino.modules.web.util import util
from hoshino.modules.web.api import api
from hoshino.modules.web.api import login

app: FastAPI = nonebot.get_app()
app.include_router(api.router)
app.include_router(login.router)
@app.get("/")
async def root():
    return {"message": "Hello Bigger Applications!"}

# 设置拦截
@app.middleware('http')
async def _(req: Request, call_next: Callable):
    path = req.scope['path']
    if path == '/login': # 访问登录  路由不拦截
        resp = await call_next(req)
        return resp
    else:
        headers = req.headers
        if not 'token' in headers:
            logger.info('request api without access token')
            return Response(status_code=401, content='no token')
        token = headers['token']
        if not util.check_auth(token):
            return Response(status_code=401, content='wrong token or token expired')
        resp = await call_next(req)
        return resp

origins = [
    "http://localhost",
    "http://localhost:8080"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)