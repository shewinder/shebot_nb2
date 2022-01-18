from hoshino.pluginconfig import PluginConfig, BaseConfig
from hoshino import conf_dir

class Config(BaseConfig):                                                                           
    appid: str = ''
    key: str = ''

plugin_config = PluginConfig('translate', conf_dir.joinpath('translate.json'), Config())
