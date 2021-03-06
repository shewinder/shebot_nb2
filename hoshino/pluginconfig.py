from pathlib import Path
from typing import Any, Dict, Union

from pydantic import BaseModel

from hoshino.util.sutil import save_config, load_config

_all_plugin_config: Dict[str, "PluginConfig"] = {} # 所有插件的配置数据

class BaseConfig(BaseModel):
    pass

    
class PluginConfig:
    def __init__(self, 
            plugin_name: str,
            json_file: Union[Path, str],
            config: BaseConfig) -> None:
        self._plugin_name = plugin_name
        self._json_file = json_file
        self._config = self.load_json(config) if self.load_json(config) else config # 优先读取配置文件
        if not Path(json_file).exists():
            self.save_json()
        _all_plugin_config[plugin_name] = self

    @property
    def config(self) -> BaseConfig:
        return self._config
    
    @property
    def plugin_name(self) -> str:
        return self._plugin_name

    @property
    def json_file(self) -> Union[Path, str]:
        return self._json_file

    def load_json(self, model):
        # model 传入了一个BaseConfig的子类
        config = load_config(self.json_file)
        return model.__class__(**config) if config else None


    def save_json(self) -> None:
        save_config(self.config.dict(), self.json_file)

    def set(self, key, value) -> None:
        """
        插件的config设置接口
        """
        if key not in self.config.__dict__:
            raise KeyError
        self.config.__dict__[key] = value
        self.save_json()

    def __repr__(self) -> str:
        return self.config.dict().__str__()
    
    def __str__(self) -> str:
        return self.__repr__()

    def __getattr__(self, name):
        return self.config.__dict__.get(name).value

def get_plugin_config() -> Dict[str, PluginConfig]:
    return _all_plugin_config

        





