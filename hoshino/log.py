'''
Author: AkiraXie
Date: 2021-02-22 02:35:32
LastEditors: AkiraXie
LastEditTime: 2021-03-04 22:23:41
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot.log import logger
import os
import sys
from . import hsn_config
from .service import _loaded_matchers


class wrap_logger:
    def __init__(self, name: str) -> None:
        self.name = name

    def exception(self, message: str, exception=True):
        return logger.opt(colors=True, exception=exception).exception(
            f"<r><ly>{self.name}</> | {message}</>")

    def error(self, message: str, exception=True):
        return logger.opt(colors=True, exception=exception).error(
            f"<r><ly>{self.name}</> | {message}</>")

    def critical(self, message: str):
        return logger.opt(colors=True).critical(
            f"<ly>{self.name}</> | {message}")

    def warning(self, message: str):
        return logger.opt(colors=True).warning(
            f"<ly>{self.name}</> | {message}")

    def success(self, message: str):
        return logger.opt(colors=True).success(
            f"<ly>{self.name}</> | {message}")

    def info(self, message: str):
        return logger.opt(colors=True).info(
            f"<ly>{self.name}</> | {message}")

    def debug(self, message: str):
        return logger.opt(colors=True).debug(
            f"<ly>{self.name}</> | {message}")


class Filter:
    '''
    改自 ``nonebot.log.Filter``
    '''

    def __init__(self) -> None:
        self.level = "DEBUG"

    def __call__(self, record: dict):
        record["name"] = record["name"].split(".")[0]
        levelno = logger.level(self.level).no
        nologmatchers = map(str, _loaded_matchers.keys())
        nologmatchers = set(nologmatchers)
        nologmatchers.add('type=Message.message')
        nologflag = not any(
            nologmatcher in record['message'] for nologmatcher in nologmatchers)
        return record["level"].no >= levelno and nologflag


log_root = hsn_config.data + '/logs/'
os.makedirs(log_root, exist_ok=True)
logger.remove()
hoshino_filter = Filter()
hoshino_filter.level = 'DEBUG' if hsn_config.debug else "INFO"
default_format = (
    "<g>{time:MM-DD HH:mm:ss}</g> "
    "[<lvl>{level}</lvl>] "
    "<c><u>{name}</u></c> | "
    "{message}")
logger.add(sys.stdout,
           colorize=True,
           diagnose=False,
           filter=hoshino_filter,
           format=default_format)
logger.add(log_root+'hsn{time:YYYYMMDD}.log', rotation='00:00', level='INFO')
logger.add(log_root+'hsn{time:YYYYMMDD}_error.log',
           rotation='00:00', level='ERROR')
