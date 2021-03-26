from pathlib import Path
from hoshino.pluginconfig import PluginConfig, BaseConfig

class Config(BaseConfig):                                                                           
    appid: str = ''
    key: str = ''

plugin_config = PluginConfig('translate', Path(__file__).parent.joinpath('config.json'), Config())
