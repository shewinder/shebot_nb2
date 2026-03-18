"""
AI Chat Web 管理 API
提供模型切换、人格管理等功能
"""
from typing import Dict, List, Optional, Set
from fastapi import APIRouter, File, UploadFile, Form
from pydantic import BaseModel
from nonebot import get_driver
from loguru import logger

import nonebot
from hoshino import Bot
from hoshino.config import get_plugin_config_by_name
from hoshino.modules.interactive.aichat import api_manager, persona_manager, conf
from hoshino.modules.interactive.aichat.config import ApiEntry
from hoshino.modules.interactive.aichat.character_import import parse_character_png, CharacterCard
import json

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
    api_key: str
    is_current: bool
    is_default: bool
    supports_multimodal: Optional[bool] = None


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
            api_key=api.api_key,
            is_current=api.id == current_id,
            is_default=api.id == default_id,
            supports_multimodal=api.supports_multimodal
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
        api_key=entry.api_key,
        is_current=True,
        is_default=api_id == conf.get_default_api_id(),
        supports_multimodal=entry.supports_multimodal
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


class AddModelRequest(BaseModel):
    """添加模型请求"""
    id: str
    name: str
    api_base: str
    api_key: str
    model: str
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    supports_multimodal: Optional[bool] = None


class UpdateModelRequest(BaseModel):
    """更新模型请求"""
    name: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    supports_multimodal: Optional[bool] = None


@router.post("/add-model")
async def add_model(req: AddModelRequest):
    """添加新模型"""
    # 检查 ID 是否已存在
    if conf.get_api_by_id(req.id):
        return {"status": 400, "data": f"模型 ID '{req.id}' 已存在"}
    
    # 创建新的 API Entry
    new_api = ApiEntry(
        id=req.id,
        name=req.name,
        api_base=req.api_base,
        api_key=req.api_key,
        model=req.model,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        supports_multimodal=req.supports_multimodal
    )
    
    # 添加到配置
    conf.apis.append(new_api)
    
    try:
        # 保存配置
        from hoshino.config import save_plugin_config
        save_plugin_config("aichat", conf)
        return {"status": 200, "data": f"模型 '{req.name}' 添加成功"}
    except Exception as e:
        logger.exception(f"添加模型失败: {e}")
        return {"status": 500, "data": f"保存配置失败: {str(e)}"}


@router.post("/update-model/{model_id}")
async def update_model(model_id: str, req: UpdateModelRequest):
    """更新模型配置"""
    api_entry = conf.get_api_by_id(model_id)
    if not api_entry:
        return {"status": 404, "data": f"未找到模型: {model_id}"}
    
    # 更新字段（空字符串表示不修改）
    if req.name is not None:
        api_entry.name = req.name
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
    
    try:
        from hoshino.config import save_plugin_config
        save_plugin_config("aichat", conf)
        return {"status": 200, "data": f"模型 '{api_entry.name}' 更新成功"}
    except Exception as e:
        logger.exception(f"更新模型失败: {e}")
        return {"status": 500, "data": f"保存配置失败: {str(e)}"}


@router.post("/delete-model/{model_id}")
async def delete_model(model_id: str):
    """删除模型"""
    api_entry = conf.get_api_by_id(model_id)
    if not api_entry:
        return {"status": 404, "data": f"未找到模型: {model_id}"}
    
    # 不能删除当前正在使用的模型
    current_id = api_manager.get_current_api_id()
    if model_id == current_id:
        return {"status": 400, "data": "不能删除当前正在使用的模型，请先切换到其他模型"}
    
    # 不能删除默认模型
    if model_id == conf.get_default_api_id():
        return {"status": 400, "data": "不能删除默认模型，请先将其他模型设为默认"}
    
    # 从列表中移除
    conf.apis = [a for a in conf.apis if a.id != model_id]
    
    try:
        from hoshino.config import save_plugin_config
        save_plugin_config("aichat", conf)
        return {"status": 200, "data": f"模型 '{api_entry.name}' 删除成功"}
    except Exception as e:
        logger.exception(f"删除模型失败: {e}")
        return {"status": 500, "data": f"保存配置失败: {str(e)}"}


@router.post("/set-default-model/{model_id}")
async def set_default_model(model_id: str):
    """设置默认模型"""
    if not conf.get_api_by_id(model_id):
        return {"status": 404, "data": f"未找到模型: {model_id}"}
    
    conf.default_api = model_id
    
    try:
        from hoshino.config import save_plugin_config
        save_plugin_config("aichat", conf)
        return {"status": 200, "data": f"已将模型设为默认"}
    except Exception as e:
        logger.exception(f"设置默认模型失败: {e}")
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
