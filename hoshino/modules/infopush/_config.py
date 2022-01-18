from typing import List, Set

from hoshino import conf_dir
from hoshino.pluginconfig import PluginConfig, BaseConfig

class Config(BaseConfig):
    PROXY_POOL_URL = 'http://81.70.165.122:5555/random'

plugin_config = PluginConfig('infopush', conf_dir.joinpath('infopush.json'), Config())