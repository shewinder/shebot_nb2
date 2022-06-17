import asyncio
import importlib
import os
import pathlib
from itertools import groupby
from typing import List

from hoshino import add_job
from hoshino.log import logger

from hoshino.modules.infopush._model import BaseInfoChecker, Subscribe, get_sub_data, refresh_subdata
# init data
refresh_subdata()


checker_dir = pathlib.Path(__file__).parent.joinpath('checkers')

for module_name in os.listdir(checker_dir):
    try:
        if module_name.startswith('__'): # 排除__pycache__
            continue
        if not module_name.endswith('.py'):
            continue
        m = importlib.import_module(f'hoshino.modules.infopush.checkers.{module_name.rstrip(".py")}')
    except:
        logger.error(f'error occured when importing {module_name}')

checkers = BaseInfoChecker.get_all_checkers()
print("test info", checkers)
checker_groups = groupby(sorted(checkers, key=lambda x: getattr(x, 'seconds')), 
                        key=lambda x: getattr(x, 'seconds'))

async def check(checkers: List[BaseInfoChecker]):
    global sub_data
    sub_data = get_sub_data()
    if not sub_data:
        logger.info('当前没有任何订阅')
        return
    for checker in checkers:
        logger.info(f'{checker.__name__} start checking')
        subs: List["Subscribe"] = sub_data.get(checker.__name__)
        if not subs:
            logger.info(f'{checker.__name__} 当前无订阅')
            continue
        for sub in subs:
            logger.info(f'checking {sub.remark}')
            updated, data = await checker.check(sub)
            if updated:
                await checker.notice(sub, data)
            logger.info('checking complete')
            await asyncio.sleep(checker.seconds / len(subs) - 1)       

for seconds, checker_group in checker_groups:
    add_job(check, 
            trigger='interval', 
            args = [[i for i in checker_group]],
            id = f'信息推送{seconds}秒档',
            max_instances = 10,
            seconds=seconds)
