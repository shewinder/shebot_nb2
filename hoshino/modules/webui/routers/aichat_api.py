"""
AI Chat Web 管理 API
提供模型切换、人格管理等功能
"""
from typing import Dict, List, Optional, Set
from fastapi import APIRouter
from pydantic import BaseModel
from nonebot import get_driver
from loguru import logger

import nonebot
from hoshino import Bot
from hoshino.config import get_plugin_config_by_name
from hoshino.modules.interactive.aichat import api_manager, persona_manager, conf
from hoshino.modules.interactive.aichat.config import ApiEntry

# 从 NoneBot 配置获取超级用户
def get_superusers() -> Set[int]:
    """获取超级用户列表"""
    driver = get_driver()
    superusers = getattr(driver.config, 'superusers', set())
    # 转换为整数集合
    return {int(uid) for uid in superusers}

router = APIRouter(prefix="/aichat")


class ModelInfo(BaseModel):
    """模型信息"""
    id: str
    name: str
    model: str
    api_base: str
    is_current: bool
    is_default: bool


class PersonaInfo(BaseModel):
    """人格信息"""
    id: str
    type: str  # "user", "group", "global", "config"
    content: Optional[str]
    effective: bool


class SwitchModelRequest(BaseModel):
    """切换模型请求"""
    api_id: str


class SetPersonaRequest(BaseModel):
    """设置人格请求"""
    type: str  # "global", "group", "user"
    group_id: Optional[int] = None
    user_id: Optional[int] = None
    content: str


class SavedPersona(BaseModel):
    """已保存的人格"""
    name: str
    content: str


@router.get("/models")
async def get_models():
    """获取所有可用的模型列表"""
    apis = conf.get_api_list()
    current_id = api_manager.get_current_api_id()
    default_id = conf.get_default_api_id()
    
    result = []
    for api in apis:
        result.append(ModelInfo(
            id=api.id,
            name=api.name,
            model=api.model,
            api_base=api.api_base,
            is_current=api.id == current_id,
            is_default=api.id == default_id
        ))
    
    return {"status": 200, "data": result}


@router.get("/current-model")
async def get_current_model():
    """获取当前使用的模型"""
    api_id = api_manager.get_current_api_id()
    entry = conf.get_api_by_id(api_id)
    if not entry:
        return {"status": 404, "data": None}
    
    return {"status": 200, "data": ModelInfo(
        id=entry.id,
        name=entry.name,
        model=entry.model,
        api_base=entry.api_base,
        is_current=True,
        is_default=api_id == conf.get_default_api_id()
    )}


@router.post("/switch-model")
async def switch_model(req: SwitchModelRequest):
    """切换当前使用的模型"""
    if not conf.get_api_by_id(req.api_id):
        return {"status": 400, "data": f"未找到模型: {req.api_id}"}
    
    success = api_manager.set_current_api_id(req.api_id)
    if success:
        entry = conf.get_api_by_id(req.api_id)
        return {"status": 200, "data": f"已切换到模型: {entry.name} ({entry.model})"}
    else:
        return {"status": 500, "data": "切换模型失败"}


@router.get("/personas")
async def get_personas(group_id: Optional[int] = None, user_id: Optional[int] = None):
    """获取人格列表
    
    如果提供了 user_id，返回该用户的人格层级信息
    如果不提供 group_id，则返回该用户在所有群组中的人格设置
    """
    if user_id:
        # 获取指定群组上下文的人格层级
        info = persona_manager.get_user_persona_info(user_id, group_id)
        
        # 如果没有指定群组，额外获取该用户在所有群组中的人格
        all_user_personas = []
        if not group_id:
            for key, value in persona_manager.personas.items():
                # 匹配用户人格格式: {user_id}_{group_id}
                if key.startswith(f"{user_id}_"):
                    gid = key.replace(f"{user_id}_", "")
                    try:
                        gid = int(gid)
                        all_user_personas.append({
                            "group_id": gid,
                            "persona": value[:100] + "..." if len(value) > 100 else value,
                            "full_persona": value
                        })
                    except ValueError:
                        pass
                # 匹配私聊人格格式: private_{user_id}
                elif key == f"private_{user_id}":
                    all_user_personas.append({
                        "group_id": None,
                        "is_private": True,
                        "persona": value[:100] + "..." if len(value) > 100 else value,
                        "full_persona": value
                    })
        
        info["all_user_personas"] = all_user_personas
        return {"status": 200, "data": info}
    
    # 返回全局人格
    global_persona = persona_manager.personas.get("global_default")
    return {"status": 200, "data": {
        "global": global_persona,
        "config": conf.default_persona if conf.default_persona else None
    }}


@router.post("/set-global-persona")
async def set_global_persona(req: SetPersonaRequest):
    """设置全局默认人格"""
    if req.type != "global":
        return {"status": 400, "data": "类型必须是 global"}
    
    if not req.content or not req.content.strip():
        return {"status": 400, "data": "人格内容不能为空"}
    
    try:
        persona_manager.set_global_default_persona(req.content)
        return {"status": 200, "data": "全局默认人格设置成功"}
    except Exception as e:
        logger.exception(f"设置全局人格失败: {e}")
        return {"status": 500, "data": f"保存失败: {str(e)}"}


@router.post("/set-group-persona")
async def set_group_persona(req: SetPersonaRequest):
    """设置群组默认人格"""
    if req.type != "group":
        return {"status": 400, "data": "类型必须是 group"}
    
    if not req.group_id:
        return {"status": 400, "data": "必须提供 group_id"}
    
    persona_manager.set_group_default_persona(req.group_id, req.content)
    return {"status": 200, "data": f"群组 {req.group_id} 默认人格设置成功"}


@router.post("/clear-persona")
async def clear_persona(type: str, group_id: Optional[int] = None, user_id: Optional[int] = None):
    """清除人格设置"""
    if type == "global":
        if "global_default" in persona_manager.personas:
            del persona_manager.personas["global_default"]
            persona_manager.save_personas()
        return {"status": 200, "data": "全局默认人格已清除"}
    
    elif type == "group":
        if not group_id:
            return {"status": 400, "data": "必须提供 group_id"}
        group_persona_id = f"group_{group_id}"
        if group_persona_id in persona_manager.personas:
            del persona_manager.personas[group_persona_id]
            persona_manager.save_personas()
        return {"status": 200, "data": f"群组 {group_id} 默认人格已清除"}
    
    elif type == "user":
        if not user_id:
            return {"status": 400, "data": "必须提供 user_id"}
        user_persona_id = f"{user_id}_{group_id}" if group_id else f"private_{user_id}"
        if user_persona_id in persona_manager.personas:
            del persona_manager.personas[user_persona_id]
            persona_manager.save_personas()
        return {"status": 200, "data": "用户人格已清除"}
    
    return {"status": 400, "data": "无效的类型"}


@router.get("/saved-personas")
async def get_saved_personas(user_id: int):
    """获取用户保存的人格列表"""
    personas = persona_manager.get_saved_personas(user_id)
    result = [
        SavedPersona(name=name, content=content)
        for name, content in personas.items()
    ]
    return {"status": 200, "data": result}


@router.post("/save-persona")
async def save_persona(user_id: int, name: str, content: str):
    """保存人格"""
    success, msg = persona_manager.save_persona(user_id, None, name, content)
    if success:
        return {"status": 200, "data": msg}
    else:
        return {"status": 400, "data": msg}


@router.post("/delete-saved-persona")
async def delete_saved_persona(user_id: int, name: str):
    """删除保存的人格"""
    success, msg = persona_manager.delete_saved_persona(user_id, None, name)
    if success:
        return {"status": 200, "data": msg}
    else:
        return {"status": 400, "data": msg}


class ApiConfigUpdate(BaseModel):
    """更新 API 配置请求"""
    apis: List[ApiEntry]
    default_api: str


@router.get("/config")
async def get_aichat_config():
    """获取 AI Chat 完整配置"""
    config = get_plugin_config_by_name("aichat")
    if not config:
        return {"status": 404, "data": "配置未找到"}
    
    return {"status": 200, "data": config.dict()}


@router.post("/update-config")
async def update_aichat_config(config_update: Dict):
    """更新 AI Chat 配置"""
    config = get_plugin_config_by_name("aichat")
    if not config:
        return {"status": 404, "data": "配置未找到"}
    
    try:
        config.update(config_update)
        return {"status": 200, "data": "配置更新成功"}
    except Exception as e:
        return {"status": 500, "data": f"配置更新失败: {str(e)}"}


@router.get("/superusers")
async def get_superusers_list():
    """获取超级用户列表（只读）
    
    第一个超级用户作为默认用户
    """
    superusers = get_superusers()
    superusers_list = sorted(list(superusers))
    
    return {
        "status": 200, 
        "data": {
            "superusers": superusers_list,
            "first_superuser": superusers_list[0] if superusers_list else None,
            "count": len(superusers_list)
        }
    }


@router.get("/groups")
async def get_groups():
    """获取机器人加入的群组列表"""
    try:
        bot: Bot = list(nonebot.get_bots().values())[0]  # 获取第一个bot对象
    except IndexError:
        return {"status": 500, "data": "Bot未连接"}
    
    try:
        group_list = await bot.get_group_list()
        # 获取已设置人格的群组
        group_personas = {}
        for key, value in persona_manager.personas.items():
            if key.startswith("group_"):
                try:
                    group_id = int(key.replace("group_", ""))
                    group_personas[group_id] = value[:50] + "..." if len(value) > 50 else value
                except ValueError:
                    pass
        
        # 合并数据
        result = []
        for group in group_list:
            gid = group.get("group_id")
            result.append({
                "group_id": gid,
                "group_name": group.get("group_name", "未知群组"),
                "member_count": group.get("member_count", 0),
                "has_persona": gid in group_personas,
                "persona_preview": group_personas.get(gid, None)
            })
        
        return {"status": 200, "data": result}
    except Exception as e:
        return {"status": 500, "data": str(e)}
