"""
Author: AkiraXie
Date: 2021-01-28 02:03:18
LastEditors: AkiraXie
LastEditTime: 2021-02-01 14:41:36
Description: 
Github: http://github.com/AkiraXie/
"""


from pathlib import Path
import os

import nonebot

hsn_config = nonebot.get_driver().config

data_dir = Path("data")
db_dir = data_dir.joinpath("db/")
service_dir = data_dir.joinpath("service/")
os.makedirs(db_dir, exist_ok=True)
os.makedirs(service_dir, exist_ok=True)

res_dir = Path("res")
font_dir = res_dir.joinpath("fonts")
userdata_dir = data_dir
conf_dir = userdata_dir.joinpath("config")

os.makedirs(font_dir, exist_ok=True)
os.makedirs(conf_dir, exist_ok=True)


from .typing import Final
from .res import rhelper


"""
`R`本身是一个字符串，并重载了`.`,`+`,`()`等运算符,但屏蔽了对字符串本身进行修改的一些操作。

**请不要对`R`进行赋值操作！**

并且对图片对象进行了取`CQcode`和`open()`的操作。
    
e.g：
    
`R.img.priconne`==`R.img('priconne')`==`R+'img'+'priconne'`
"""
R: Final[rhelper] = rhelper()


from nonebot.adapters.cqhttp import Bot
from .util import aiohttpx, get_bot_list, sucmd, sucmds
from .message import MessageSegment, Message
from .event import Event, GroupMessageEvent, PrivateMessageEvent
from .service import Service
from .schedule import scheduled_job, add_job
from .typing import T_State
