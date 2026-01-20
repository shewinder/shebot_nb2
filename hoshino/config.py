from typing import Dict, TypeVar
from hoshino import conf_dir
from pydantic import BaseModel

_all_plugin_config: Dict[str, "BaseConfig"] = {}  # 所有插件的配置数据

T = TypeVar('T')

class BaseConfig(BaseModel):
    @classmethod
    def get_instance(cls: T, name: str) -> T:
        return _all_plugin_config[name]

def configuration(name: str):
    """
    被装饰类的实例会放到_all_plugin_config中,便于统一管理
    """
    def decorator(cls):
        cfg_file = conf_dir / f"{name}.json"
        if not cfg_file.exists():
            cfg_file.touch()
            instance: BaseModel = cls()
            cfg_file.write_text(instance.model_dump_json(indent=2))
        else:
            instance = cls.model_validate_json(cfg_file.read_text())
        _all_plugin_config[name] = instance
        return cls
    return decorator

def get_plugin_config() -> Dict[str, BaseConfig]:
    return _all_plugin_config

def get_plugin_config_by_name(plugin_name: str): 
    return _all_plugin_config.get(plugin_name)