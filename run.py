'''
Author: AkiraXie
Date: 2021-01-27 22:29:46
LastEditors: AkiraXie
LastEditTime: 2021-03-03 02:36:33
Description: 
Github: http://github.com/AkiraXie/
'''
import nonebot
import os
from typing import Dict, Set

from nonebot.adapters.onebot.v11 import Adapter


nonebot.init()
moduledir = 'hoshino/modules/'
base = 'hoshino/base/'

driver = nonebot.get_driver()
driver.register_adapter(Adapter)

config = driver.config

# if not config.modules and not config.data: 
#     env = os.environ.copy()
#     modules = parse_raw_as(Set[str], env.get('modules'))
#     data = env.get('data')
#     config.hostip = env.get("hostip")
#     apscheduler_autostart = parse_raw_as(bool, env.get('apscheduler_autostart'))
#     apscheduler_config = parse_raw_as(Dict, env.get('apscheduler_config'))
#     config.modules = modules
#     config.data = data
#     config.apscheduler_autostart = apscheduler_autostart
#     config.apscheduler_config = apscheduler_config

# 商店插件
nonebot.load_plugin("nonebot_plugin_wordle")
nonebot.load_plugin("nonebot_plugin_handle")
nonebot.load_plugin("nonebot_plugin_parser")

nonebot.load_plugins(base)
if modules := config.modules:
    for module in modules:
        module = os.path.join(moduledir, module)
        nonebot.load_plugins(module)



if __name__ == '__main__':
    nonebot.run()
