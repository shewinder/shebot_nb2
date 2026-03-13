from typing import Any, Dict

import json
import nonebot
from nonebot import get_driver
from nonebot.plugin import get_loaded_plugins
from fastapi import APIRouter, Response
from pydantic import BaseModel

from hoshino import Bot, Service
from hoshino.config import get_plugin_config, get_plugin_config_by_name
from loguru import logger

import os

router = APIRouter()


@router.get("/get_group_list")
async def get_group_list():
    try:
        bot: Bot = list(nonebot.get_bots().values())[0]  # 获取第一个bot对象
    except IndexError:
        return Response("Bot未连接", status_code=500)
    try:
        group_list = await bot.get_group_list()
        return {"status": 200, "data": group_list}
    except Exception as e:
        return Response(e, status_code=500)


@router.get("/get_loaded_services")
async def get_loaded_service():
    svs = Service.get_loaded_services()
    sv_names = list(svs.keys())
    return {"status": 200, "data": sv_names}


class GroupData(BaseModel):
    group_id: int
    group_name: str
    on: bool


@router.get("/get_service_groups/{sv_name}")
async def get_enable_groups(sv_name: str):
    svs = Service.get_loaded_services()
    bot: Bot = list(nonebot.get_bots().values())[0]
    groups = await bot.get_group_list()
    data = []
    for group in groups:
        gid = group["group_id"]
        gnm = group["group_name"]
        if svs[sv_name].check_enabled(gid):
            gd = GroupData(group_id=gid, group_name=gnm, on=True)
        else:
            gd = GroupData(group_id=gid, group_name=gnm, on=False)
        data.append(gd)
    return {"status": 200, "data": data}


@router.get("/get_group_services/{group_id}")
async def get_group_services(group_id: int):
    svs = Service.get_loaded_services()
    conf = {}
    conf[group_id] = {}
    for sv_name in svs:
        conf[group_id][sv_name] = svs[sv_name].check_enabled(group_id)
    return {"status": 200, "data": conf}


class ServiceConf(BaseModel):
    data: Dict[int, Dict[str, bool]]


@router.post("/set_service")
async def set_service(sc: ServiceConf):
    # 接收前端传来的配置数据，数据格式{"<gid>":{'serviceA':True,'serviceB':False}}
    svs = Service.get_loaded_services()
    data = sc.data
    for gid in data:
        for sv_name in data[gid]:
            if data[gid][sv_name]:
                svs[sv_name].set_enable(gid)
                logger.info(f"启用群 {gid} 服务 {sv_name} ")
            else:
                svs[sv_name].set_disable(gid)
                logger.info(f"禁用群 {gid} 服务 {sv_name}")
    return {"status": 200, "data": "SUCCESS"}


@router.get("/get_plugin_config")
async def get_config():
    configs = get_plugin_config()
    configs = {k: v.dict() for k, v in configs.items()}
    return {"status": 200, "data": configs}


class PlgConfig(BaseModel):
    name: str
    config: Dict[str, Any]


@router.post("/set_plugin")
async def set_plugin(pc: PlgConfig):
    config = get_plugin_config_by_name(pc.name)
    config.update(pc.config)
    return {"status": 200, "data": "SUCCESS"}


@router.get("/get_loaded_plugins")
async def handle_getting_plugins():
    plugins = get_loaded_plugins()

    def _plugin_to_dict(plugin):
        return {
            "name": plugin.name,
            "module": plugin.module.__file__,
            "matcher": len(plugin.matcher),
        }

    return {"status": 200, "data": list(map(_plugin_to_dict, plugins))}


class AutoEncoder(json.JSONEncoder):
    def default(self, o):
        try:
            return super().default(o)
        except Exception as e:
            return str(o)


@router.get("/get_config")
async def handle_getting_config():
    driver = get_driver()

    config = driver.config
    return {
        "status": 200,
        "data": json.loads(json.dumps(config.dict(), cls=AutoEncoder)),
    }


@router.get("/get_project_info")
async def handle_project_info():
    cwd = os.getcwd()
    return {"status": 200, "data": {"name": os.path.basename(cwd), "dir": cwd}}
