from pathlib import Path
from typing import List, Set
from hoshino.pluginconfig import PluginConfig, BaseConfig

class Config(BaseConfig):
    apikey: str = '610940955e9e90fb1372a2'                           # 填lolicon apikey
    online_mode: bool = True                                         # 选择在线模式还是本地模式,选择False时，程序将不会访问api和启动下载线程，插件发送本地涩图
    with_url: bool = False                                           # 是否发图时附带链接
    daily_max_num: int = 30                                          # 每日最大涩图数(仅在在线模式下生效)
    delete_after: int = 30                                           # 色图撤回时间，单位为s
    r18_groups: Set[int] = []                                        # 允许r18的群聊列表
    delete_groups: Set[int] = []                                     # 涩图撤回的列表
    search_strategy: int = 1                                         # 搜图策略 0 api优先 1 本地数据库优先
    exceed_notice: str = f'您今天已经冲过{daily_max_num}次了，请明早5点后再来！' 
    too_frequent_notic: str = f'您冲得太快了，请稍后再来~'

plugin_config = PluginConfig('setu', Path(__file__).parent.joinpath('config.json'), Config())



