from os import path

from hoshino import conf_dir
from hoshino.config import BaseConfig, configuration

@configuration('conhead')
class Config(BaseConfig):
    CLIENT_ID = 'dkGndecuTLxEq7NvePAz0eQk'
    CLIENT_SECRET = 'MweFIf6DeqGANH7azo0gWAFjmtAONN1B'
    DAILY_MAX_NUM = 5
    DEFAULT_MODE = 2 # 1使用百度api， 2使用opencv
