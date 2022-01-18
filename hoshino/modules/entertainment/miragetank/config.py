from os import path

from hoshino.pluginconfig import PluginConfig, BaseConfig
from hoshino import conf_dir

class Config(BaseConfig):
    daily_max_num: int = 10

plugin_config = PluginConfig('miragetank', conf_dir.joinpath('miragetank.json'), Config())

