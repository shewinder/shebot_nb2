from hoshino.pluginconfig import BaseConfig, configuration

@configuration('imagegenerator')
class Config(BaseConfig):
    initial: str = 'random'