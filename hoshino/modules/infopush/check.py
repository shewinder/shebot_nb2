import asyncio
import importlib
import os
from typing import List

import pathlib

from loguru import logger

from hoshino import scheduled_job
from hoshino.log import logger

from ._data import SubscribeRec

checker_dir = pathlib.Path(__file__).parent.joinpath('checkers')
modules = []

for module_name in os.listdir(checker_dir):
    try:
        if module_name.startswith('__'):
            continue
        m = importlib.import_module(f'hoshino.modules.infopush.checkers.{module_name.rstrip(".py")}')
        modules.append(m)
    except ImportError:
        logger.error(f'error occured when importing {module_name}')
        raise
@scheduled_job('interval', seconds=10, id='信息推送', max_instances=3)
#@scheduled_job('interval', minutes=3, id='信息推送', max_instances=3)
async def _():
    logger.info('start checking')
    subs: List[SubscribeRec] = SubscribeRec.select()
    for sub in subs:
        logger.info(f'checking {sub.remark}')
        for m in modules:
            if hasattr(m, sub.checker):
                checker = getattr(m, sub.checker)()
                await checker.check_and_notice(sub)
    logger.info('checking complete') 