import importlib
import os
from typing import Iterable, List
from itertools import groupby

import pathlib

from loguru import logger

from hoshino import scheduled_job, add_job
from hoshino.log import logger
from hoshino.glob import SUBS

from ._model import SubscribeRec, BaseInfoChecker

checker_dir = pathlib.Path(__file__).parent.joinpath('checkers')

for module_name in os.listdir(checker_dir):
    try:
        if module_name.startswith('__'):
            continue
        m = importlib.import_module(f'hoshino.modules.infopush.checkers.{module_name.rstrip(".py")}')
    except ImportError:
        logger.error(f'error occured when importing {module_name}')
        raise
checkers = BaseInfoChecker.get_all_checkers()
checker_groups = groupby(sorted(checkers, key=lambda x: getattr(x, 'seconds')), 
                        key=lambda x: getattr(x, 'seconds'))

for checker in checkers:
    subs: List[SubscribeRec] = list(SubscribeRec.select().where(SubscribeRec.checker == checker.__class__.__name__))
    SUBS[checker.__class__.__name__] = subs


async def check(checkers: List[BaseInfoChecker]):
    for checker in checkers:
        logger.info(f'{checker.__class__.__name__} start checking')
        #subs: List[SubscribeRec] = SubscribeRec.select().where(SubscribeRec.checker == checker.__class__.__name__)
        subs: List[SubscribeRec] = SUBS[checker.__class__.__name__]
        for i, sub in enumerate(subs[::-1]):
            logger.info(f'checking {sub.remark}')
            if await checker.check_and_notice(sub):
                subs[i] = sub
            logger.info('checking complete')


for seconds, checker_group in checker_groups:
    add_job(check, 
            trigger='interval', 
            args = [[i for i in checker_group]],
            id = f'信息推送{seconds}秒档',
            max_instances = 10,
            seconds=seconds)

@scheduled_job('interval', minutes=10)
async def refresh():
    logger.info('start refreshing subscribes')
    subs: List[SubscribeRec] = list(SubscribeRec.select().where(SubscribeRec.checker == checker.__class__.__name__))
    SUBS[checker.__class__.__name__] = subs
    logger.info('refreshing subscribes completed')