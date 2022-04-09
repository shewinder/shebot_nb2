from os import path
from typing import Dict

from hoshino.config import BaseConfig, configuration
from hoshino import conf_dir

@configuration('fortune')
class Config(BaseConfig):
    theme: str = 'random'
    user_theme: Dict[str, str] = {}