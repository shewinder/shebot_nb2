from os import path
from typing import Dict

from hoshino.pluginconfig import BaseConfig, PluginConfig

class Config(BaseConfig):
    theme: str = 'genshin'

plugin_config = PluginConfig('fortune', path.join(path.dirname(__file__), 'config.json'), Config())