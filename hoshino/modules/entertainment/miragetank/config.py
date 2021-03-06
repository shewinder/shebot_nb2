from os import path

from hoshino.pluginconfig import PluginConfig, BaseConfig

class Config(BaseConfig):
    daily_max_num: int = 10

plugin_config = PluginConfig('miragetank', path.join(path.dirname(__file__), 'config.json'), Config())

