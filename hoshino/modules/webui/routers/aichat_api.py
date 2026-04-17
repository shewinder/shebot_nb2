"""
AI Chat Web 管理 API
提供 API 厂商管理、模型切换、人格管理等功能
"""
import time
from typing import Dict, List, Optional, Set
from fastapi import APIRouter, File, UploadFile, Form
from pydantic import BaseModel
from nonebot import get_driver
from loguru import logger

import nonebot
from hoshino import Bot
from hoshino.config import get_plugin_config_by_name
from hoshino.modules.aichat import api_manager, persona_manager, conf, session_manager
from hoshino.modules.aichat.skills import skill_manager
from hoshino.modules.aichat.config import ApiEntry
from hoshino.modules.aichat.character_import import parse_character_png, CharacterCard
import json

# 从 NoneBot 配置获取超级用户
def get_superusers() -> Set[int]:
    """获取超级用户列表"""
    driver = get_driver()
    superusers = getattr(driver.config, 'superusers', set())
    # 转换为整数集合
    return {int(uid) for uid in superusers}

router = APIRouter(prefix="/aichat")


class ApiInfo(BaseModel):
    """API 厂商信息 - 兼容前端模型管理格式"""
    api: str                # 厂商标识
    model: str              # 模型名称
    api_base: str
    api_key: str
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    is_current: bool        # 是否当前使用
    supports_multimodal: Optional[bool] = None
    supports_tools: Optional[bool] = None


class PersonaInfo(BaseModel):
    """人格信息"""
    id: str
    type: str  # "user", "group", "global", "config"
    content: Optional[str]
    effective: bool


class SwitchApiRequest(BaseModel):
    """切换 API 厂商请求"""
    api: str


class SwitchModelRequest(BaseModel):
    """切换模型请求"""
    model: str


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


class DeleteSavedPersonaRequest(BaseModel):
    """删除保存的人格请求"""
    user_id: int
    name: str


@router.get("/apis")
async def get_apis():
    """获取所有可用的 API 厂商列表"""
    apis = conf.get_apis()
    current_api = api_manager.get_current_api()
    
    result = []
    for api in apis:
        result.append(ApiInfo(
            api=api.api,
            model=api.model,
            api_base=api.api_base,
            api_key=api.api_key,
            max_tokens=api.max_tokens,
            temperature=api.temperature,
            is_current=api.api == current_api,
            supports_multimodal=api.supports_multimodal,
            supports_tools=api.supports_tools
        ))
    
    return {"status": 200, "data": result}


@router.get("/current-api")
async def get_current_api():
    """获取当前使用的 API 厂商"""
    api_name = api_manager.get_current_api()
    entry = conf.get_api_by_name(api_name)
    if not entry:
        return {"status": 404, "data": None}
    
    return {"status": 200, "data": ApiInfo(
        api=entry.api,
        model=entry.model,
        api_base=entry.api_base,
        api_key=entry.api_key,
        max_tokens=entry.max_tokens,
        temperature=entry.temperature,
        is_current=True,
        supports_multimodal=entry.supports_multimodal,
        supports_tools=entry.supports_tools
    )}


@router.post("/switch-api")
async def switch_api(req: SwitchApiRequest):
    """切换当前使用的 API 厂商"""
    if not conf.get_api_by_name(req.api):
        return {"status": 400, "data": f"未找到 API 厂商: {req.api}"}
    
    success = api_manager.set_current_api(req.api)
    if success:
        entry = conf.get_api_by_name(req.api)
        return {"status": 200, "data": f"已切换到 API 厂商: {entry.api}，当前模型: {entry.model}"}
    else:
        return {"status": 500, "data": "切换 API 厂商失败"}


@router.get("/current-model")
async def get_current_model():
    """获取当前使用的模型"""
    api_name = api_manager.get_current_api()
    model = api_manager.get_current_model()
    return {"status": 200, "data": {"api": api_name, "model": model}}


@router.get("/available-models")
async def get_available_models():
    """获取当前 API 厂商支持的可用模型列表"""
    try:
        models = await api_manager.get_available_models()
        if not models:
            return {"status": 200, "data": [], "message": "未获取到模型列表，请检查 API 配置"}
        return {"status": 200, "data": models}
    except Exception as e:
        logger.error(f"获取可用模型列表失败: {e}")
        return {"status": 500, "data": [], "message": f"获取模型列表失败: {str(e)}"}


@router.post("/switch-model")
async def switch_model(req: SwitchModelRequest):
    """切换当前 API 厂商使用的模型"""
    success = api_manager.set_current_model(req.model)
    if success:
        return {"status": 200, "data": f"已切换到模型: {req.model}"}
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
async def delete_saved_persona(req: DeleteSavedPersonaRequest):
    """删除保存的人格"""
    success, msg = persona_manager.delete_saved_persona(req.user_id, None, req.name)
    if success:
        return {"status": 200, "data": msg}
    else:
        return {"status": 400, "data": msg}


class ApiConfigUpdate(BaseModel):
    """更新 API 配置请求"""
    apis: List[ApiEntry]
    current_api: str


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


class AddApiRequest(BaseModel):
    """添加 API 厂商请求"""
    api: str
    api_base: str
    api_key: str
    model: str
    max_tokens: int = 8192
    temperature: float = 0.7
    supports_multimodal: Optional[bool] = None
    supports_tools: Optional[bool] = True


class UpdateApiRequest(BaseModel):
    """更新 API 厂商请求"""
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    supports_multimodal: Optional[bool] = None
    supports_tools: Optional[bool] = None


@router.post("/add-api")
async def add_api(req: AddApiRequest):
    """添加新 API 厂商"""
    # 检查 api 是否已存在
    if conf.get_api_by_name(req.api):
        return {"status": 400, "data": f"API 厂商 '{req.api}' 已存在"}
    
    # 创建新的 API Entry
    new_api = ApiEntry(
        api=req.api,
        api_base=req.api_base,
        api_key=req.api_key,
        model=req.model,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        supports_multimodal=req.supports_multimodal,
        supports_tools=req.supports_tools
    )
    
    # 添加到配置
    conf.apis.append(new_api)
    
    try:
        # 保存配置
        from hoshino.config import save_plugin_config
        save_plugin_config("aichat", conf)
        return {"status": 200, "data": f"API 厂商 '{req.api}' 添加成功"}
    except Exception as e:
        logger.exception(f"添加 API 厂商失败: {e}")
        return {"status": 500, "data": f"保存配置失败: {str(e)}"}


@router.post("/update-api/{api_name}")
async def update_api(api_name: str, req: UpdateApiRequest):
    """更新 API 厂商配置"""
    api_entry = conf.get_api_by_name(api_name)
    if not api_entry:
        return {"status": 404, "data": f"未找到 API 厂商: {api_name}"}
    
    # 更新字段
    if req.api_base is not None:
        api_entry.api_base = req.api_base
    if req.api_key is not None and req.api_key.strip() != "":
        api_entry.api_key = req.api_key
    if req.model is not None:
        api_entry.model = req.model
    if req.max_tokens is not None:
        api_entry.max_tokens = req.max_tokens
    if req.temperature is not None:
        api_entry.temperature = req.temperature
    if req.supports_multimodal is not None:
        api_entry.supports_multimodal = req.supports_multimodal
    if req.supports_tools is not None:
        api_entry.supports_tools = req.supports_tools
    
    try:
        from hoshino.config import save_plugin_config
        save_plugin_config("aichat", conf)
        return {"status": 200, "data": f"API 厂商 '{api_entry.api}' 更新成功"}
    except Exception as e:
        logger.exception(f"更新 API 厂商失败: {e}")
        return {"status": 500, "data": f"保存配置失败: {str(e)}"}


@router.post("/delete-api/{api_name}")
async def delete_api(api_name: str):
    """删除 API 厂商"""
    api_entry = conf.get_api_by_name(api_name)
    if not api_entry:
        return {"status": 404, "data": f"未找到 API 厂商: {api_name}"}
    
    # 不能删除当前正在使用的 API 厂商
    current_api = api_manager.get_current_api()
    if api_name == current_api:
        return {"status": 400, "data": "不能删除当前正在使用的 API 厂商，请先切换到其他厂商"}
    
    # 从列表中移除
    conf.apis = [a for a in conf.apis if a.api != api_name]
    
    try:
        from hoshino.config import save_plugin_config
        save_plugin_config("aichat", conf)
        return {"status": 200, "data": f"API 厂商 '{api_entry.api}' 删除成功"}
    except Exception as e:
        logger.exception(f"删除 API 厂商失败: {e}")
        return {"status": 500, "data": f"保存配置失败: {str(e)}"}


# ========== 全局预设人格管理 API ==========

class GlobalPreset(BaseModel):
    """全局预设人格"""
    name: str
    content: str


class AddGlobalPresetRequest(BaseModel):
    """添加全局预设人格请求"""
    name: str
    content: str


@router.get("/global-presets")
async def get_global_presets():
    """获取所有全局预设人格"""
    presets = persona_manager.get_global_presets()
    result = [
        GlobalPreset(name=name, content=content)
        for name, content in presets.items()
    ]
    return {"status": 200, "data": result}


@router.post("/add-global-preset")
async def add_global_preset(req: AddGlobalPresetRequest):
    """添加或更新全局预设人格"""
    if not req.name or not req.name.strip():
        return {"status": 400, "data": "预设人格名称不能为空"}
    if not req.content or not req.content.strip():
        return {"status": 400, "data": "预设人格内容不能为空"}
    
    success, msg = persona_manager.add_global_preset(req.name, req.content)
    if success:
        return {"status": 200, "data": msg}
    else:
        return {"status": 400, "data": msg}


class UpdateGlobalPresetNameRequest(BaseModel):
    """修改全局预设人格名称请求"""
    old_name: str
    new_name: str


@router.post("/update-global-preset-name")
async def update_global_preset_name(req: UpdateGlobalPresetNameRequest):
    """修改全局预设人格名称"""
    success, msg = persona_manager.update_global_preset_name(req.old_name, req.new_name)
    if success:
        return {"status": 200, "data": msg}
    else:
        return {"status": 400, "data": msg}


@router.post("/delete-global-preset")
async def delete_global_preset(name: str):
    """删除全局预设人格"""
    if not name or not name.strip():
        return {"status": 400, "data": "预设人格名称不能为空"}
    
    success, msg = persona_manager.delete_global_preset(name.strip())
    if success:
        return {"status": 200, "data": msg}
    else:
        return {"status": 404, "data": msg}


# ========== 角色卡导入 API ==========

class CharacterImportResult(BaseModel):
    """角色卡导入结果"""
    name: str
    success: bool
    message: str


def _parse_character_file(content: bytes, file_name: str) -> tuple:
    """
    解析角色卡文件（支持 JSON 和 PNG 格式）
    
    Returns:
        (success: bool, char_card: CharacterCard|None, message: str)
    """
    # 判断文件类型
    is_json = file_name.lower().endswith('.json')
    is_png = file_name.lower().endswith('.png')
    
    if not is_json and not is_png:
        # 尝试根据内容判断
        if content.startswith(b'{') or content.startswith(b'['):
            is_json = True
        elif content.startswith(b'\x89PNG'):
            is_png = True
        else:
            return False, None, "不支持的文件格式，请上传 JSON 或 PNG 文件"
    
    if is_json:
        # 解析 JSON
        try:
            json_str = content.decode('utf-8')
            data = json.loads(json_str)
            
            if not isinstance(data, dict):
                return False, None, "JSON 格式错误：应为对象"
            
            # 检查 name 字段（支持标准格式和 chara_card_v2 嵌套格式）
            card_data = data.get('data', data)  # 如果是 v2 格式，使用 data 字段
            if 'name' not in card_data:
                return False, None, "JSON 中未找到 'name' 字段，不是有效的角色卡"
            
            char_card = CharacterCard(data)
            return True, char_card, f"成功解析 JSON 角色卡：{char_card.name}"
        except json.JSONDecodeError as e:
            return False, None, f"JSON 解析错误：{e}"
        except UnicodeDecodeError:
            return False, None, "文件编码错误，请使用 UTF-8 编码"
    
    elif is_png:
        # 解析 PNG
        return parse_character_png(content)
    
    return False, None, "未知的文件类型"


@router.post("/import-character")
async def import_character(
    user_id: int = Form(...),
    files: List[UploadFile] = File(...),
    as_global: bool = Form(False)
):
    """
    从 PNG 图片或 JSON 文件导入角色卡
    
    Args:
        user_id: 用户ID
        files: 上传的文件列表（支持 PNG 和 JSON）
        as_global: 是否保存为全局预设（需要超级用户权限）
    
    Returns:
        导入结果列表
    """
    # 检查超级用户权限
    if as_global and user_id not in get_superusers():
        return {"status": 403, "data": "只有超级用户可以导入全局预设人格"}
    
    if not files:
        return {"status": 400, "data": "未上传文件"}
    
    results = []
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    for file in files:
        file_name = file.filename or "unknown"
        
        try:
            # 读取文件内容
            content = await file.read()
            if not content:
                results.append(CharacterImportResult(
                    name=file_name,
                    success=False,
                    message="文件内容为空"
                ))
                fail_count += 1
                continue
            
            # 尝试解析角色卡（支持 JSON 和 PNG）
            success, char_card, msg = _parse_character_file(content, file_name)
            
            if not success or not char_card:
                # 解析失败
                skip_count += 1
                results.append(CharacterImportResult(
                    name=file_name,
                    success=False,
                    message=f"不是有效的角色卡: {msg}"
                ))
                continue
            
            # 转换为角色人格
            persona_name = char_card.name
            persona_text = char_card.to_persona_text()
            
            # 保存人格
            if as_global:
                success_save, msg_save = persona_manager.add_global_preset(persona_name, persona_text)
            else:
                success_save, msg_save = persona_manager.save_persona(user_id, None, persona_name, persona_text)
            
            if success_save:
                success_count += 1
                results.append(CharacterImportResult(
                    name=persona_name,
                    success=True,
                    message=msg_save
                ))
            else:
                fail_count += 1
                results.append(CharacterImportResult(
                    name=persona_name,
                    success=False,
                    message=msg_save
                ))
                
        except Exception as e:
            logger.exception(f"导入角色卡失败: {e}")
            fail_count += 1
            results.append(CharacterImportResult(
                name=file_name,
                success=False,
                message=f"处理异常: {str(e)}"
            ))
        finally:
            await file.close()
    
    return {
        "status": 200,
        "data": {
            "results": results,
            "summary": {
                "total": len(files),
                "success": success_count,
                "failed": fail_count,
                "skipped": skip_count
            }
        }
    }


@router.post("/import-character-single")
async def import_character_single(
    user_id: int = Form(...),
    file: UploadFile = File(...),
    as_global: bool = Form(False)
):
    """
    从单个文件导入角色卡（简化版，支持 JSON 和 PNG）
    
    Args:
        user_id: 用户ID
        file: 上传的文件（JSON 或 PNG）
        as_global: 是否保存为全局预设
    
    Returns:
        导入结果，包含角色卡详细信息
    """
    # 检查超级用户权限
    if as_global and user_id not in get_superusers():
        return {"status": 403, "data": "只有超级用户可以导入全局预设人格"}
    
    file_name = file.filename or "unknown"
    
    try:
        content = await file.read()
        if not content:
            return {"status": 400, "data": "文件内容为空"}
        
        # 解析角色卡（支持 JSON 和 PNG）
        success, char_card, msg = _parse_character_file(content, file_name)
        
        if not success or not char_card:
            return {"status": 400, "data": f"解析失败: {msg}"}
        
        # 转换为角色人格
        persona_name = char_card.name
        persona_text = char_card.to_persona_text()
        
        # 保存人格
        if as_global:
            success_save, msg_save = persona_manager.add_global_preset(persona_name, persona_text)
        else:
            success_save, msg_save = persona_manager.save_persona(user_id, None, persona_name, persona_text)
        
        if success_save:
            return {
                "status": 200,
                "data": {
                    "name": persona_name,
                    "description": char_card.description[:200] + "..." if len(char_card.description) > 200 else char_card.description,
                    "personality": char_card.personality,
                    "scenario": char_card.scenario,
                    "creator": char_card.creator,
                    "tags": char_card.tags if isinstance(char_card.tags, list) else [],
                    "content_length": len(persona_text),
                    "message": msg_save,
                    "is_global": as_global
                }
            }
        else:
            return {"status": 400, "data": msg_save}
            
    except Exception as e:
        logger.exception(f"导入角色卡失败: {e}")
        return {"status": 500, "data": f"导入失败: {str(e)}"}
    finally:
        await file.close()



# ========== Session 调试 API ==========

from hoshino.modules.aichat.session import Session


class SessionInfo(BaseModel):
    """Session 信息"""
    session_id: str
    user_id: int
    group_id: Optional[int]
    type: str  # "group" 或 "private"
    message_count: int
    user_images: int
    ai_images: int
    continuous_mode: bool
    choice_mode: bool
    last_active: str
    is_expired: bool


@router.get("/sessions")
async def get_sessions():
    """获取所有活跃 Session 列表"""
    try:
        sessions = []
        for session_id, session in session_manager.sessions.items():
            # 解析 session_id 获取 user_id 和 group_id
            user_id = 0
            group_id = None
            session_type = "private"
            
            if session_id.startswith("group_"):
                # group_{group_id}_user_{user_id}
                parts = session_id.split("_")
                if len(parts) >= 4:
                    try:
                        group_id = int(parts[1])
                        user_id = int(parts[3])
                        session_type = "group"
                    except (ValueError, IndexError):
                        pass
            elif session_id.startswith("private_"):
                # private_{user_id}
                try:
                    user_id = int(session_id.replace("private_", ""))
                except ValueError:
                    pass
            
            sessions.append(SessionInfo(
                session_id=session_id,
                user_id=user_id,
                group_id=group_id,
                type=session_type,
                message_count=len(session.messages),
                user_images=len(session._user_images),
                ai_images=len(session._ai_images),
                continuous_mode=session.continuous_mode,
                choice_mode=False,
                last_active=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(session.last_active)),
                is_expired=session.is_expired()
            ))
        
        return {"status": 200, "data": {"sessions": sessions, "total": len(sessions)}}
    except Exception as e:
        logger.exception(f"获取 Session 列表失败: {e}")
        return {"status": 500, "data": f"获取失败: {str(e)}"}


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """获取指定 Session 详情"""
    try:
        session = session_manager.sessions.get(session_id)
        if not session:
            return {"status": 404, "data": "Session 不存在"}
        
        # 解析 session_id
        user_id = 0
        group_id = None
        if session_id.startswith("group_"):
            parts = session_id.split("_")
            if len(parts) >= 4:
                try:
                    group_id = int(parts[1])
                    user_id = int(parts[3])
                except (ValueError, IndexError):
                    pass
        elif session_id.startswith("private_"):
            try:
                user_id = int(session_id.replace("private_", ""))
            except ValueError:
                pass
        
        # 处理 messages，保留完整内容
        messages = []
        for msg in session.messages:
            content = msg.get("content", "")
            content_display = content
            if isinstance(content, list):
                # 多模态消息，简化展示
                content_display = f"[多模态消息，共{len(content)}个部分]"
            
            messages.append({
                "role": msg.get("role"),
                "content": content_display
            })
        
        # 获取人格
        persona = ""
        if session.messages and session.messages[0].get("role") == "system":
            persona = session.messages[0].get("content", "")
            if not isinstance(persona, str):
                persona = ""
        
        return {
            "status": 200,
            "data": {
                "session_id": session_id,
                "user_id": user_id,
                "group_id": group_id,
                "messages": messages,
                "message_count": len(session.messages),
                "user_images": list(session._user_images.keys()),
                "ai_images": list(session._ai_images.keys()),
                "continuous_mode": session.continuous_mode,
                "choice_mode": False,
                "choice_guideline": "",
                "last_choices": session.last_choices,
                "last_active": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(session.last_active)),
                "is_expired": session.is_expired(),
                "persona": persona
            }
        }
    except Exception as e:
        logger.exception(f"获取 Session 详情失败: {e}")
        return {"status": 500, "data": f"获取失败: {str(e)}"}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除指定 Session"""
    try:
        if session_id not in session_manager.sessions:
            return {"status": 404, "data": "Session 不存在"}
        
        del session_manager.sessions[session_id]
        logger.info(f"已删除 Session: {session_id}")
        return {"status": 200, "data": f"Session {session_id} 已删除"}
    except Exception as e:
        logger.exception(f"删除 Session 失败: {e}")
        return {"status": 500, "data": f"删除失败: {str(e)}"}


@router.post("/sessions/cleanup-expired")
async def cleanup_expired_sessions():
    """清理所有过期的 Session"""
    try:
        expired_count = 0
        expired_sessions = []
        
        for session_id, session in list(session_manager.sessions.items()):
            if session.is_expired():
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del session_manager.sessions[session_id]
            expired_count += 1
        
        logger.info(f"清理了 {expired_count} 个过期 Session")
        return {"status": 200, "data": f"已清理 {expired_count} 个过期 Session"}
    except Exception as e:
        logger.exception(f"清理过期 Session 失败: {e}")
        return {"status": 500, "data": f"清理失败: {str(e)}"}


# ========== SKILL 管理 API ==========

class SkillInfo(BaseModel):
    """SKILL 信息"""
    name: str
    description: str
    allowed_tools: List[str]
    user_invocable: bool
    disable_model_invocation: bool
    source: str
    version: str
    enabled: bool


class SkillConfig(BaseModel):
    """SKILL 配置"""
    enable_skills: bool
    skill_user_paths: List[str]


@router.get("/skills")
async def get_skills():
    """获取所有可用 SKILL 列表"""
    try:
        if not conf.enable_skills:
            return {"status": 200, "data": [], "message": "SKILL 系统未启用"}
        
        # 确保 skill_manager 已初始化
        if not skill_manager._initialized:
            skill_manager.user_paths = conf.skill_user_paths
            skill_manager.initialize()
        
        skills = skill_manager.list_skills()
        result = [
            SkillInfo(
                name=skill.metadata.name,
                description=skill.metadata.description,
                allowed_tools=skill.metadata.allowed_tools,
                user_invocable=skill.metadata.user_invocable,
                disable_model_invocation=skill.metadata.disable_model_invocation,
                source=skill.metadata.source,
                version=skill.metadata.version,
                enabled=skill.metadata.enabled
            )
            for skill in skills
        ]
        return {"status": 200, "data": result}
    except Exception as e:
        logger.exception(f"获取 SKILL 列表失败: {e}")
        return {"status": 500, "data": f"获取失败: {str(e)}"}



@router.get("/config/skills")
async def get_skills_config():
    """获取 SKILL 系统配置"""
    try:
        return {
            "status": 200,
            "data": {
                "enable_skills": conf.enable_skills,
                "skill_user_paths": conf.skill_user_paths
            }
        }
    except Exception as e:
        logger.exception(f"获取 SKILL 配置失败: {e}")
        return {"status": 500, "data": f"获取失败: {str(e)}"}


@router.post("/config/skills")
async def update_skills_config(config_update: SkillConfig):
    """更新 SKILL 系统配置"""
    try:
        # 更新配置
        conf.enable_skills = config_update.enable_skills
        conf.skill_user_paths = config_update.skill_user_paths
        
        # 保存配置
        from hoshino.config import save_plugin_config
        save_plugin_config("aichat", conf)
        
        # 如果 SKILL 系统被启用，重新初始化 skill_manager
        if conf.enable_skills:
            skill_manager.user_paths = conf.skill_user_paths
            skill_manager.reload()
        
        return {"status": 200, "data": "SKILL 配置更新成功"}
    except Exception as e:
        logger.exception(f"更新 SKILL 配置失败: {e}")
        return {"status": 500, "data": f"更新失败: {str(e)}"}
