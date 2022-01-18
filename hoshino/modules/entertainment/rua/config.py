from os import path

from hoshino.pluginconfig import PluginConfig, BaseConfig
from hoshino import conf_dir

class Config(BaseConfig):
    daily_max_num: int = 10

plugin_config = PluginConfig('rua', conf_dir.joinpath('rua.json'), Config())

