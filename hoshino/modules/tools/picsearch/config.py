from hoshino.config import BaseConfig, configuration

@configuration('picsearch')
class Config(BaseConfig):
    soucenao_apikey: str = ''  # soucenao apikey
    proxy: str = ''




