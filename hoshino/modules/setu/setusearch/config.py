from hoshino.config import configuration, BaseConfig

@configuration('setu_search')
class Config(BaseConfig):

    """
    0 for yande first; 1 for pixiv first; 2 for mix
    """
    mode: int = 0