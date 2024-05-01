from hoshino.log import logger
from ._util import check_auth
from typing import Callable
import nonebot
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request, Response

from hoshino.modules.web.routers.custom_reply import router as custom_reply_router
from hoshino.modules.web.routers.infopush_api import router as infopush_router
from hoshino.modules.web.routers.bot_manage import router as bot_manage_router
from hoshino.modules.web.routers.login import router as login_router
from hoshino.modules.web.routers.public import router as public_router

app: FastAPI = nonebot.get_app()

app.include_router(login_router)
app.include_router(bot_manage_router)
app.include_router(custom_reply_router)
app.include_router(infopush_router)
app.include_router(public_router)

_whitelist = ["/login", "/public"]

@app.middleware("http")
async def _(req: Request, call_next: Callable):
    path: str = req.scope["path"]
    for p in _whitelist:
        if path.startswith(p):
            resp = await call_next(req)
            return resp
    else:
        # headers = req.headers
        # if not 'token' in headers:
        #     logger.info('request api without access token')
        #     return Response(status_code=401, content='no token')
        # token = headers['token']
        # if not check_auth(token):
        #     return Response(status_code=401, content='wrong token or token expired')
        resp = await call_next(req)
        return resp


# origins = [
#     "http://localhost",
#     "http://localhost:8080"
# ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
