from typing import Dict
from hoshino.config import BaseConfig, configuration

@configuration('imagegenerator')
class Config(BaseConfig):
    initial: str = 'random'
    user: Dict[str, str] = {}
