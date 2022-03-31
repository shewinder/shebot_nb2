from pathlib import Path
from typing import Any, Dict, TypeVar, Union, Type

from pydantic import BaseModel

from hoshino.util.sutil import save_config, load_config
from hoshino import conf_dir
from functools import wraps

_all_plugin_config: Dict[str, "PluginConfig"] = {}  # 所有插件的配置数据


class BaseConfig(BaseModel):
    pass


class PluginConfig:
    def __init__(
        self, plugin_name: str, json_file: Union[Path, str], config: BaseConfig
    ) -> None:
        self._plugin_name = plugin_name
        self._json_file = json_file

        if isinstance(json_file, str):
            json_file = Path(json_file)
        if json_file.exists():
            self._config = self.load_json(config)  # 优先读取配置文件
        else:
            self._config = config
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

def get_plugin_config_by_name(plugin_name: str): 
    return _all_plugin_config.get(plugin_name).config

def configuration (name: str):
    def decorator(cls):
        PluginConfig(name, conf_dir / f"{name}.json", cls())
        return cls
    return decorator