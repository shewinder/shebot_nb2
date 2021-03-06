from os import path

from hoshino.pluginconfig import PluginConfig, BaseConfig

class Config(BaseConfig):
    daily_max_num: int = 10
    exceed_notice: str = '您今天已经迫害多次了，手下留情吧~'

plugin_config = PluginConfig('teasedragonking', path.join(path.dirname(__file__), 'config.json'), Config())

