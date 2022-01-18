from pathlib import Path
from typing import List, Set
from hoshino.pluginconfig import PluginConfig, BaseConfig
from hoshino import conf_dir

class Config(BaseConfig):
    soucenao_apikey: str = '0a9d3bd4068fe8be95ae1ce20320b01c3a69440b'  # soucenao apikey
    proxy: str = ''

plugin_config = PluginConfig('picsearch', conf_dir.joinpath('picsearch.json'), Config())



