from typing import Dict, TypeVar
from hoshino.util.persist import Persistent
from hoshino import conf_dir

_all_plugin_config: Dict[str, "BaseConfig"] = {}  # 所有插件的配置数据

T = TypeVar('T')

class BaseConfig(Persistent):
    """
    继承自Persistent，一个和json文件绑定的类
    任何对对象的修改都会触发json dump
    """
    @classmethod
    def get_instance(cls: T, name: str) -> T:
        return _all_plugin_config[name]

def configuration (name: str):
    """
    被装饰类的实例会放到_all_plugin_config中,便于统一管理
    """
    def decorator(cls):
        _all_plugin_config[name] = cls(conf_dir / f"{name}.json")
        return cls
    return decorator

def get_plugin_config() -> Dict[str, BaseConfig]:
    return _all_plugin_config

def get_plugin_config_by_name(plugin_name: str): 
    return _all_plugin_config.get(plugin_name)