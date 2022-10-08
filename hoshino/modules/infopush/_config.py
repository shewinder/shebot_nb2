from typing import Dict, List
from hoshino.config import BaseConfig, configuration

@configuration('infopush')
class Config(BaseConfig):
    PROXY_POOL_URL = 'http://81.70.165.122:5555/random'
    rsshub_url: str = 'http://rsshub.shewinder.win/'
    fanbox_cookies: Dict[int, str] = {}