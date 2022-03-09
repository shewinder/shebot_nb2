from os import path
from typing import Dict

from hoshino.pluginconfig import BaseConfig, PluginConfig
from hoshino import conf_dir

class Config(BaseConfig):
    theme: str = 'random'

plugin_config = PluginConfig('fortune', conf_dir.joinpath('fortune.json'), Config())