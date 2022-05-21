from os import path

from hoshino.config import BaseConfig, configuration
from hoshino import conf_dir

@configuration('teasedragonking')
class Config(BaseConfig):
    daily_max_num: int = 3
    exceed_notice: str = '您今天已经迫害多次了，手下留情吧~'

