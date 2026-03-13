import io
from typing import List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from hoshino.modules.customreply._data import CustomReply
from hoshino.util import aiorequests
import re
import nonebot


router = APIRouter(prefix="/public")

@router.get("/qqimg")
async def rehost(url: str):
    resp = await aiorequests.get(url)
    cont = await resp.content
    return StreamingResponse(io.BytesIO(cont), media_type="image/png")
