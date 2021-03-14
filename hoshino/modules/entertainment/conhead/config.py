from os import path

from hoshino.pluginconfig import BaseConfig, PluginConfig

class Config(BaseConfig):
    CLIENT_ID = ''
    CLIENT_SECRET = ''
    DAILY_MAX_NUM = 5
    DEFAULT_MODE = 2 # 1使用百度api， 2使用opencv

plugin_config = PluginConfig('conhead', path.join(path.dirname(__file__), 'config.json'), Config())