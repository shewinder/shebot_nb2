from os import path
from typing import Dict

from hoshino.pluginconfig import BaseConfig, PluginConfig
from hoshino import conf_dir

class Config(BaseConfig):
    initial: str = 'aqua'

plugin_config = PluginConfig('imagegenerator', conf_dir.joinpath('imagegenerator.json'), Config())