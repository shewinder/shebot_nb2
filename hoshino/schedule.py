from functools import wraps
from typing import Dict, Optional
from nonebot_plugin_apscheduler import scheduler
from loguru import logger
from apscheduler import job
from .typing import Callable, Any, Awaitable


def wrapper(func: Callable[[], Any], id: str, args, kwargs: Dict=None) -> Callable[[], Awaitable[Any]]:
    if not args:
        args = []
    if not kwargs:
        kwargs = {}
    @wraps(func)
    async def _wrapper() -> Awaitable[Any]:
        try:
            logger.opt(colors=True).info(
                f'<ly>Scheduled job <c>{id}</c> started.</ly>')
            res = await func(*args, **kwargs)
            logger.opt(colors=True).info(
                f'<ly>Scheduled job <c>{id}</c> completed.</ly>')
            return res
        except Exception as e:
            logger.opt(colors=True, exception=e).error(
                f'<r><bg #f8bbd0>Scheduled job <c>{id}</c> failed.</bg #f8bbd0></r>')
    return _wrapper


def scheduled_job(trigger: str, args=None, kwargs=None, **trigger_kwargs):
    def deco(func: Callable[[], Any]) -> Callable[[], Awaitable[Any]]:
        id = trigger_kwargs.get('id', func.__name__)
        trigger_kwargs['id'] = id
        return scheduler.scheduled_job(trigger, args=args, kwargs=kwargs, **trigger_kwargs)(wrapper(func, id, args, kwargs))
    return deco


def add_job(func: Callable[[], Any], trigger: str, args=None, kwargs: Optional[Dict]=None, **trigger_kwargs)->job.Job:
    id = trigger_kwargs.get('id', func.__name__)
    trigger_kwargs['id'] = id
    return scheduler.add_job(wrapper(func, id, args, kwargs), trigger, **trigger_kwargs)
    #return scheduler.add_job(func, trigger, **kwargs)
