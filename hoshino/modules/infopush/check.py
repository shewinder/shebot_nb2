import importlib
import os
import pathlib
from itertools import groupby
from typing import Dict, Iterable, List

from hoshino import add_job
from hoshino.log import logger
from loguru import logger

from ._glob import SUBS
from ._model import BaseInfoChecker, SubscribeRecord

checker_dir = pathlib.Path(__file__).parent.joinpath('checkers')

for module_name in os.listdir(checker_dir):
    try:
        if module_name.startswith('__'): # 排除__pycache__
            continue
        m = importlib.import_module(f'hoshino.modules.infopush.checkers.{module_name.rstrip(".py")}')
    except ImportError:
        logger.error(f'error occured when importing {module_name}')
        raise
checkers = BaseInfoChecker.get_all_checkers()
checker_groups = groupby(sorted(checkers, key=lambda x: getattr(x, 'seconds')), 
                        key=lambda x: getattr(x, 'seconds'))


SubscribeRecord.init()

async def check(checkers: List[BaseInfoChecker]):
    if not SUBS:
        logger.info('当前没有任何订阅')
        return
    for checker in checkers:
        logger.info(f'{checker.__class__.__name__} start checking')
        subs: Dict[str, "SubscribeRecord"] = SUBS.get(checker.__class__.__name__)
        if not subs:
            logger.info(f'{checker.__class__.__name__} 当前无订阅')
            continue
        for url in list(subs):
            sub = subs[url]
            logger.info(f'checking {sub.remark}')
            if await checker.check_and_notice(sub):
                sub.save()
            logger.info('checking complete')


for seconds, checker_group in checker_groups:
    add_job(check, 
            trigger='interval', 
            args = [[i for i in checker_group]],
            id = f'信息推送{seconds}秒档',
            max_instances = 10,
            seconds=seconds)
