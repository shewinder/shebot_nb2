import importlib
import os
import pathlib
from itertools import groupby
from typing import List

from hoshino import add_job
from hoshino.log import logger

from ._model import BaseInfoChecker, SubscribeRecord, sub_data

checker_dir = pathlib.Path(__file__).parent.joinpath('checkers')

for module_name in os.listdir(checker_dir):
    try:
        if module_name.startswith('__'): # 排除__pycache__
            continue
        if not module_name.endswith('.py'):
            continue
        m = importlib.import_module(f'hoshino.modules.infopush.checkers.{module_name.rstrip(".py")}')
    except ImportError:
        logger.error(f'error occured when importing {module_name}')

checkers = BaseInfoChecker.get_all_checkers()
checker_groups = groupby(sorted(checkers, key=lambda x: getattr(x, 'seconds')), 
                        key=lambda x: getattr(x, 'seconds'))

async def check(checkers: List[BaseInfoChecker]):
    if not sub_data:
        logger.info('当前没有任何订阅')
        return
    for checker in checkers:
        logger.info(f'{checker.__class__.__name__} start checking')
        subs: List["SubscribeRecord"] = sub_data.data.get(checker.__class__.__name__)
        if not subs:
            logger.info(f'{checker.__class__.__name__} 当前无订阅')
            continue
        for sub in subs:
            logger.info(f'checking {sub.remark}')
            updated, data = await checker.check(sub)
            if updated:
                await checker.notice(sub, data)
            logger.info('checking complete')         

for seconds, checker_group in checker_groups:
    add_job(check, 
            trigger='interval', 
            args = [[i for i in checker_group]],
            id = f'信息推送{seconds}秒档',
            max_instances = 10,
            seconds=seconds)
