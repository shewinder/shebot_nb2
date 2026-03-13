from hoshino.log import logger
from ._util import check_auth
from typing import Callable
import nonebot
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from .routers.infopush_api import router as infopush_router
from .routers.bot_manage import router as bot_manage_router
from .routers.login import router as login_router
from .routers.public import router as public_router
from .routers.websocket import router as ws_router

# 静态文件目录（插件目录下的 static/）
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
_static_dir = os.path.join(_plugin_dir, "static")

def init_web():
    """初始化 Web 服务"""
    app: FastAPI = nonebot.get_app()

    # 注册 API 路由（添加 /api 前缀）
    app.include_router(login_router, prefix="/api")
    app.include_router(bot_manage_router, prefix="/api")
    app.include_router(infopush_router, prefix="/api")
    app.include_router(public_router, prefix="/api")
    app.include_router(ws_router, prefix="/api")

    # 挂载静态文件（如果存在）
    if os.path.exists(_static_dir):
        app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="assets")
        logger.info(f"[WebUI] Static files mounted at {_static_dir}")

    # API 白名单（不需要 token）
    _whitelist = ["/api/login", "/api/public", "/assets", "/vite.svg"]

    @app.middleware("http")
    async def _(req: Request, call_next: Callable):
        path: str = req.scope["path"]
        
        # 静态文件和页面请求不检查 token
        for p in _whitelist:
            if path.startswith(p):
                resp = await call_next(req)
                return resp
        
        # 根路径返回 index.html
        if path == "/" or path == "/index.html":
            index_path = os.path.join(_static_dir, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            else:
                return Response("Web UI not built. Run: cd web && npm run build", status_code=404)
        
        # API 请求检查 token（暂时注释掉，按需启用）
        # headers = req.headers
        # if not 'token' in headers:
        #     logger.info('request api without access token')
        #     return Response(status_code=401, content='no token')
        # token = headers['token']
        # if not check_auth(token):
        #     return Response(status_code=401, content='wrong token or token expired')
        
        resp = await call_next(req)
        return resp


# 可选：启用 CORS
# origins = [
#     "http://localhost",
#     "http://localhost:3000",
#     "http://localhost:8080"
# ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
