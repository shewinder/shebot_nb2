from hoshino.pluginconfig import BaseConfig, PluginConfig
from hoshino import conf_dir

class Config(BaseConfig):
    initial: str = 'random'

plugin_config = PluginConfig('imagegenerator', conf_dir.joinpath('imagegenerator.json'), Config())