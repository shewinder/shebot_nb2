from hoshino.config import BaseConfig, configuration

@configuration('pixivrank')
class Config(BaseConfig):
    hour: int = 18 # after 18:00 to ensure the rank is up-to-date
    minute: int = 30 # less than 55 because r18 rank is  minutes later