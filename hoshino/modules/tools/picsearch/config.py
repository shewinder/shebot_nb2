from pathlib import Path
from typing import List, Set
from hoshino.pluginconfig import PluginConfig, BaseConfig
from hoshino import conf_dir

class Config(BaseConfig):
    soucenao_apikey: str = ''  # soucenao apikey
    proxy: str = ''

plugin_config = PluginConfig('picsearch', conf_dir.joinpath('picsearch.json'), Config())



