from typing import List, Set

from hoshino import conf_dir
from hoshino.config import BaseConfig, configuration

@configuration('setu')
class Config(BaseConfig):
    online_mode: bool = True                                         # 选择在线模式还是本地模式,选择False时，程序将不会访问api和启动下载线程，插件发送本地涩图
    daily_max_num: int = 30                                          # 每日最大涩图数(仅在在线模式下生效)
    delete_after: int = 30                                           # 色图撤回时间，单位为s
    r18_groups: List[int] = []                                        # 允许r18的群聊列表
    delete_groups: List[int] = []                                     # 涩图撤回的列表
    search_strategy: int = 1                                         # 搜图策略 0 api优先 1 本地数据库优先
    exceed_notice: str = f'您今天已经冲过{daily_max_num}次了，请明早5点后再来！' 
    too_frequent_notic: str = f'您冲得太快了，请稍后再来~'
    proxy_site: str = 'https://pixiv.shewinder.win/'



