from os import path

from hoshino.pluginconfig import PluginConfig, BaseConfig
from hoshino import conf_dir

class Config(BaseConfig):
    daily_max_num: int = 3
    exceed_notice: str = '您今天已经迫害多次了，手下留情吧~'

plugin_config = PluginConfig('teasedragonking', conf_dir.joinpath('teasedragonking.json'), Config())

