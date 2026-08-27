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

from dotenv import load_dotenv
from nonebot.adapters.onebot.v11 import Adapter

# 显式加载 .env.prod，确保环境变量进入 os.environ（供 Skill 脚本继承）
load_dotenv('.env.prod')

nonebot.init()
moduledir = 'hoshino/modules/'
base = 'hoshino/base/'

driver = nonebot.get_driver()
driver.register_adapter(Adapter)

config = driver.config


# 商店插件：加载并登记（新增插件只改这里加一行）
from hoshino.compat import load_nb_plugin
load_nb_plugin("nonebot_plugin_wordle")
load_nb_plugin("nonebot_plugin_handle")
load_nb_plugin("nonebot_plugin_parser")

nonebot.load_plugins(base)
if modules := config.modules:
    for module in modules:
        module = os.path.join(moduledir, module)
        nonebot.load_plugins(module)

# 商店插件的 matcher 归入同名 Service（群开关 / lssv / enable / disable 可用）
from hoshino.compat import bind_plugin_matchers
bind_plugin_matchers()
# 部分插件在 on_startup 阶段才动态注册 matcher（如 parser 的链接解析），
# 启动时再补绑一次（幂等，只绑定新增的）
driver.on_startup(bind_plugin_matchers)


if __name__ == '__main__':
    nonebot.run()
