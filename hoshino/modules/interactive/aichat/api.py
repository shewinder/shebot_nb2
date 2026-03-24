"""
API 管理模块
管理大模型 API 配置和选择
"""
import json
from typing import Any, Dict, Optional
from pathlib import Path
from loguru import logger

from hoshino import userdata_dir, conf_dir
from hoshino.config import save_plugin_config
from .config import Config

# 加载配置
conf = Config.get_instance('aichat')

# 运行时数据目录（data/aichat）
aichat_data_dir: Path = userdata_dir.joinpath('aichat')


def _migrate_config():
    """迁移旧配置到新格式"""
    cfg_file = conf_dir / "aichat.json"
    if not cfg_file.exists():
        return
    
    try:
        with open(cfg_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 检测旧配置格式
        needs_migration = False
        
        # 检查是否有旧字段
        if "default_api" in data or "max_saved_personas" in data or "markdown_preview_length" in data:
            needs_migration = True
        
        # 检查 apis 中的字段
        if "apis" in data and len(data["apis"]) > 0:
            first_api = data["apis"][0]
            if "id" in first_api or "name" in first_api:
                needs_migration = True
        
        if not needs_migration:
            return
        
        logger.info("检测到旧版配置，开始迁移...")
        
        # 迁移 apis 列表
        new_apis = []
        for old_api in data.get("apis", []):
            new_api = {
                "api": old_api.get("id") or old_api.get("name", ""),
                "api_base": old_api.get("api_base", ""),
                "api_key": old_api.get("api_key", ""),
                "model": old_api.get("model", ""),
                "supports_multimodal": old_api.get("supports_multimodal"),
                "supports_tools": old_api.get("supports_tools", True),
            }
            # 迁移 max_tokens 和 temperature（从旧 entry 或全局）
            if old_api.get("max_tokens") is not None:
                new_api["max_tokens"] = old_api["max_tokens"]
            else:
                new_api["max_tokens"] = data.get("max_tokens", 8192)
            
            if old_api.get("temperature") is not None:
                new_api["temperature"] = old_api["temperature"]
            else:
                new_api["temperature"] = data.get("temperature", 0.7)
            
            new_apis.append(new_api)
        
        # 构建新配置
        new_config = {
            "apis": new_apis,
            "current_api": data.get("current_api", ""),
            "max_history": data.get("max_history", 100),
            "session_timeout": data.get("session_timeout", 3600),
            "default_persona": data.get("default_persona", ""),
            "enable_markdown_render": data.get("enable_markdown_render", True),
            "markdown_min_length": data.get("markdown_min_length", 100),
        }
        
        # 如果没有 current_api，尝试从 default_api 或旧数据文件迁移
        if not new_config["current_api"]:
            # 尝试从旧 default_api 迁移
            if data.get("default_api"):
                new_config["current_api"] = data["default_api"]
            else:
                # 尝试从旧数据文件迁移
                old_data_file = aichat_data_dir.joinpath('aichat_api_selection.json')
                if old_data_file.exists():
                    try:
                        with open(old_data_file, 'r', encoding='utf-8') as f:
                            old_data = json.load(f)
                        if isinstance(old_data, dict) and "current_api" in old_data:
                            new_config["current_api"] = old_data["current_api"]
                    except Exception:
                        pass
        
        # 保存新配置
        with open(cfg_file, 'w', encoding='utf-8') as f:
            json.dump(new_config, f, ensure_ascii=False, indent=2)
        
        logger.info("配置迁移完成")
        
        # 重新加载配置
        global conf
        conf = Config.get_instance('aichat')
        
    except Exception as e:
        logger.error(f"配置迁移失败: {e}")


# 执行配置迁移
_migrate_config()


def _build_api_config_dict(api_entry) -> Dict[str, Any]:
    """从 ApiEntry 构建完整 API 调用参数字典"""
    config_dict = {
        "api_base": api_entry.api_base,
        "api_key": api_entry.api_key,
        "model": api_entry.model,
        "max_tokens": api_entry.max_tokens,
        "temperature": api_entry.temperature,
        "supports_multimodal": api_entry.supports_multimodal if api_entry.supports_multimodal is not None else False,
        "supports_tools": api_entry.supports_tools if api_entry.supports_tools is not None else False,
    }
    return config_dict


class ApiManager:
    """管理当前使用的大模型 API（全局唯一）"""
    
    def get_current_api(self) -> str:
        """获取当前厂商"""
        return conf.get_current_api()
    
    def set_current_api(self, api: str) -> bool:
        """切换厂商"""
        if not conf.set_current_api(api):
            return False
        save_plugin_config("aichat", conf)
        return True
    
    def get_current_model(self) -> str:
        """获取当前厂商使用的模型"""
        api = self.get_current_api()
        entry = conf.get_api_by_name(api)
        return entry.model if entry else ""
    
    def set_current_model(self, model: str) -> bool:
        """修改当前厂商的模型"""
        api = self.get_current_api()
        entry = conf.get_api_by_name(api)
        if not entry:
            return False
        entry.model = model
        save_plugin_config("aichat", conf)
        return True
    
    def get_api_config(self) -> Optional[Dict[str, Any]]:
        """获取当前应使用的 API 配置"""
        api = self.get_current_api()
        entry = conf.get_api_by_name(api)
        if not entry:
            return None
        return _build_api_config_dict(entry)


# 全局 API 管理器
api_manager = ApiManager()
