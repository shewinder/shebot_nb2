"""人格管理模块"""
import json
from typing import Dict, Optional, Tuple
from pathlib import Path
from loguru import logger

from hoshino import userdata_dir
from .config import Config

conf = Config.get_instance('aichat')
aichat_data_dir: Path = userdata_dir.joinpath('aichat')


class PersonaManager:
    def __init__(self):
        self.personas: Dict[str, str] = {}  # key: persona_id, value: persona_text
        self.saved_personas: Dict[str, Dict[str, str]] = {}  # key: user_id, value: {name: persona_text}
        self.global_presets: Dict[str, str] = {}  # key: preset_name, value: persona_text (全局预设人格)
        self.data_file = aichat_data_dir.joinpath('aichat_personas.json')
        self.saved_personas_file = aichat_data_dir.joinpath('aichat_saved_personas.json')
        self.global_presets_file = aichat_data_dir.joinpath('aichat_global_presets.json')
        self.load_personas()
        self.load_saved_personas()
        self.load_global_presets()
    
    def _get_user_persona_id(self, user_id: int, group_id: Optional[int] = None) -> str:
        if group_id:
            return f"{user_id}_{group_id}"
        return f"private_{user_id}"
    
    def _get_group_persona_id(self, group_id: int) -> str:
        return f"group_{group_id}"
    
    def _get_global_persona_id(self) -> str:
        return "global_default"
    
    def get_persona(self, user_id: int, group_id: Optional[int] = None) -> Optional[str]:
        user_persona_id = self._get_user_persona_id(user_id, group_id)
        if user_persona_id in self.personas:
            persona = self.personas[user_persona_id]
            if persona and persona.strip():
                return persona.strip()
        
        if group_id:
            group_persona_id = self._get_group_persona_id(group_id)
            if group_persona_id in self.personas:
                persona = self.personas[group_persona_id]
                if persona and persona.strip():
                    return persona.strip()
        
        global_persona_id = self._get_global_persona_id()
        if global_persona_id in self.personas:
            persona = self.personas[global_persona_id]
            if persona and persona.strip():
                return persona.strip()
        
        if conf.default_persona and conf.default_persona.strip():
            return conf.default_persona.strip()
        
        return None
    
    def set_user_persona(self, user_id: int, group_id: Optional[int], persona: str) -> bool:
        user_persona_id = self._get_user_persona_id(user_id, group_id)
        self.personas[user_persona_id] = persona.strip()
        self.save_personas()
        return True
    
    def set_group_default_persona(self, group_id: int, persona: str) -> bool:
        group_persona_id = self._get_group_persona_id(group_id)
        self.personas[group_persona_id] = persona.strip()
        self.save_personas()
        return True
    
    def set_global_default_persona(self, persona: str) -> bool:
        global_persona_id = self._get_global_persona_id()
        self.personas[global_persona_id] = persona.strip()
        self.save_personas()
        return True
    
    def clear_user_persona(self, user_id: int, group_id: Optional[int] = None) -> bool:
        user_persona_id = self._get_user_persona_id(user_id, group_id)
        if user_persona_id in self.personas:
            del self.personas[user_persona_id]
            self.save_personas()
            return True
        return False
    
    def get_user_persona_info(self, user_id: int, group_id: Optional[int] = None) -> Dict[str, Optional[str]]:
        user_persona_id = self._get_user_persona_id(user_id, group_id)
        user_persona = self.personas.get(user_persona_id)
        
        group_persona = None
        if group_id:
            group_persona_id = self._get_group_persona_id(group_id)
            group_persona = self.personas.get(group_persona_id)
        
        global_persona_id = self._get_global_persona_id()
        global_persona = self.personas.get(global_persona_id)
        
        config_persona = conf.default_persona if conf.default_persona else None
        
        return {
            "user": user_persona,
            "group": group_persona,
            "global": global_persona,
            "config": config_persona,
            "effective": self.get_persona(user_id, group_id)
        }
    
    def save_personas(self):
        try:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.personas, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception(f"保存人格设置失败: {e}")
    
    def load_personas(self):
        try:
            if not self.data_file.exists():
                return
            
            with open(self.data_file, 'r', encoding='utf-8') as f:
                self.personas = json.load(f)
        except Exception as e:
            logger.error(f"加载人格设置失败: {e}")
            self.personas = {}
    
    def _get_user_key(self, user_id: int, group_id: Optional[int] = None) -> str:
        return str(user_id)
    
    def save_persona(self, user_id: int, group_id: Optional[int], name: str, persona: str) -> Tuple[bool, str]:
        user_key = self._get_user_key(user_id, group_id)
        if not name or not name.strip():
            return False, "人格名称不能为空"
        
        name = name.strip()
        
        if user_key not in self.saved_personas:
            self.saved_personas[user_key] = {}
        
        user_personas = self.saved_personas[user_key]
        
        # 保存人格（更新或新增）
        is_update = name in user_personas
        user_personas[name] = persona.strip()
        self.save_saved_personas()
        if is_update:
            return True, f"人格 '{name}' 已更新"
        return True, f"人格 '{name}' 已保存"
    
    def get_saved_personas(self, user_id: int, group_id: Optional[int] = None) -> Dict[str, str]:
        user_key = self._get_user_key(user_id, group_id)
        return self.saved_personas.get(user_key, {}).copy()
    
    def get_saved_persona(self, user_id: int, group_id: Optional[int], name: str) -> Optional[str]:
        user_key = self._get_user_key(user_id, group_id)
        user_personas = self.saved_personas.get(user_key, {})
        return user_personas.get(name)
    
    def delete_saved_persona(self, user_id: int, group_id: Optional[int], name: str) -> Tuple[bool, str]:
        user_key = self._get_user_key(user_id, group_id)
        
        if user_key not in self.saved_personas:
            return False, "未找到保存的人格"
        
        user_personas = self.saved_personas[user_key]
        
        if name not in user_personas:
            return False, f"未找到名为 '{name}' 的人格"
        
        del user_personas[name]
        
        if not user_personas:
            del self.saved_personas[user_key]
        
        self.save_saved_personas()
        return True, f"人格 '{name}' 已删除"
    
    def save_saved_personas(self):
        try:
            self.saved_personas_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.saved_personas_file, 'w', encoding='utf-8') as f:
                json.dump(self.saved_personas, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存用户人格列表失败: {e}")
    
    def load_saved_personas(self):
        try:
            if not self.saved_personas_file.exists():
                return
            
            with open(self.saved_personas_file, 'r', encoding='utf-8') as f:
                self.saved_personas = json.load(f)
        except Exception as e:
            logger.error(f"加载用户人格列表失败: {e}")
            self.saved_personas = {}

    def get_global_preset(self, name: str) -> Optional[str]:
        return self.global_presets.get(name.strip())
    
    def get_global_presets(self) -> Dict[str, str]:
        return self.global_presets.copy()
    
    def add_global_preset(self, name: str, persona: str) -> Tuple[bool, str]:
        name = name.strip()
        if not name:
            return False, "预设人格名称不能为空"
        if not persona or not persona.strip():
            return False, "预设人格内容不能为空"
        
        is_update = name in self.global_presets
        self.global_presets[name] = persona.strip()
        self.save_global_presets()
        
        if is_update:
            return True, f"全局预设人格 '{name}' 已更新"
        return True, f"全局预设人格 '{name}' 已添加"
    
    def update_global_preset_name(self, old_name: str, new_name: str) -> Tuple[bool, str]:
        old_name = old_name.strip()
        new_name = new_name.strip()
        
        if not old_name or not new_name:
            return False, "人格名称不能为空"
        
        if old_name not in self.global_presets:
            return False, f"未找到全局预设人格 '{old_name}'"
        
        if old_name == new_name:
            return True, "人格名称未变更"
        
        if new_name in self.global_presets:
            return False, f"全局预设人格 '{new_name}' 已存在"
        
        self.global_presets[new_name] = self.global_presets[old_name]
        del self.global_presets[old_name]
        self.save_global_presets()
        return True, f"全局预设人格 '{old_name}' 已重命名为 '{new_name}'"
    
    def delete_global_preset(self, name: str) -> Tuple[bool, str]:
        name = name.strip()
        if name not in self.global_presets:
            return False, f"未找到全局预设人格 '{name}'"
        
        del self.global_presets[name]
        self.save_global_presets()
        return True, f"全局预设人格 '{name}' 已删除"
    
    def save_global_presets(self):
        try:
            self.global_presets_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.global_presets_file, 'w', encoding='utf-8') as f:
                json.dump(self.global_presets, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存全局预设人格失败: {e}")
    
    def load_global_presets(self):
        try:
            if not self.global_presets_file.exists():
                self.global_presets = {}
                return
            
            with open(self.global_presets_file, 'r', encoding='utf-8') as f:
                self.global_presets = json.load(f)
        except Exception as e:
            logger.error(f"加载全局预设人格失败: {e}")
            self.global_presets = {}
    
    def find_persona_by_name(self, user_id: int, group_id: Optional[int], name: str) -> Optional[str]:
        name = name.strip()
        user_saved = self.get_saved_persona(user_id, group_id, name)
        if user_saved:
            return user_saved
        
        global_preset = self.get_global_preset(name)
        if global_preset:
            return global_preset
        
        return None


persona_manager = PersonaManager()
