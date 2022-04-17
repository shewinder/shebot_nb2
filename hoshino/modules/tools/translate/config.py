from hoshino.pluginconfig import BaseConfig, configuration

@configuration('translate')
class Config(BaseConfig):                                                                           
    appid: str = ''
    key: str = ''

