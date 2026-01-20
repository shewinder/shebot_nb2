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


# 商店插件
nonebot.load_plugin("nonebot_plugin_wordle")
nonebot.load_plugin("nonebot_plugin_handle")
nonebot.load_plugin("nonebot_plugin_parser")
# nonebot.load_plugin("nonebot_plugin_today_in_history")
# nonebot.load_plugin("nonebot_plugin_fortune")

nonebot.load_plugins(base)
if modules := config.modules:
    for module in modules:
        module = os.path.join(moduledir, module)
        nonebot.load_plugins(module)



if __name__ == '__main__':
    nonebot.run()
