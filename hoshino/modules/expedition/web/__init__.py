import nonebot
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

app: FastAPI = nonebot.get_app()

app.mount("/data/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get('/help', response_class=HTMLResponse)
async def help(request: Request):
    return templates.TemplateResponse("help.html", {'request': request})

@app.get('/show_signup')
async def _():
    return {'data', }