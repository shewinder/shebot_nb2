from pathlib import Path
from hoshino.pluginconfig import PluginConfig, BaseConfig

class Config(BaseConfig):                                       
    daily_max_num: int = 5                                       
    exceed_notice: str = f'您今天已经冲过了，请明早5点后再来！' 

plugin_config = PluginConfig('poke', Path(__file__).parent.joinpath('config.json'), Config())



