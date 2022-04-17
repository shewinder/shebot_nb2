from os import path

from hoshino.config import BaseConfig, configuration

@configuration('miragetank')
class Config(BaseConfig):
    daily_max_num: int = 10


