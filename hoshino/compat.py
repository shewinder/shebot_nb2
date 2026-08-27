"""
NoneBot 插件 ↔ hoshino Service 兼容桥

商店插件（如 nonebot_plugin_wordle）的 matcher 原本游离在 Service 体系外：
无群组开关（check_service）、不在 lssv / enable / disable 管理范围、
没有 sv.logger。本模块把这些插件的 matcher 按插件名归入同名 Service
（自动创建），并追加群开关规则。

用法（run.py，新增商店插件只改一处 load_nb_plugin 即可）::

    from hoshino.compat import load_nb_plugin, bind_plugin_matchers

    load_nb_plugin("nonebot_plugin_wordle")
    load_nb_plugin("nonebot_plugin_handle")

    # ... 其他 load_plugins ...

    bind_plugin_matchers()

只绑定 load_nb_plugin 登记过的插件，避免接管项目自己的 hoshino 模块
（base/modules 中未挂 Service 的裸 matcher 保持原状）。

自研插件如需定制管理权限/可见性，可先创建 Service 再显式绑定::

    from hoshino import Service
    from hoshino.compat import bind_matcher
    sv = Service('myplugin', manage_perm=OWNER, visible=False)
    bind_matcher(matcher, sv)
"""
import itertools
import re
from typing import Iterable, List, Optional, Type

import nonebot
from loguru import logger

from .matcher import Matcher
from .service import Service, matcher_wrapper, _loaded_matchers, _loaded_services

# 商店插件常见前缀（nonebot_plugin_wordle → wordle；nonebot_parser → parser）
_NB_PREFIX_RE = re.compile(r"^nonebot(?:_plugin)?_")

# load_nb_plugin 登记过的插件名（bind_plugin_matchers 无参时的绑定范围）
_registered_plugins: List[str] = []


def service_name_for(plugin_name: str) -> str:
    """插件名 → Service 名：去掉 nonebot_plugin_/nonebot_ 前缀"""
    name = _NB_PREFIX_RE.sub("", plugin_name)
    return name or plugin_name


def load_nb_plugin(plugin_name: str):
    """加载商店插件并登记到兼容桥白名单

    等价于 nonebot.load_plugin，额外登记插件名供 bind_plugin_matchers()
    无参调用时绑定。新增商店插件只需调用本函数，无需再改绑定处。
    """
    plugin = nonebot.load_plugin(plugin_name)
    if plugin is not None and plugin.name not in _registered_plugins:
        _registered_plugins.append(plugin.name)
    return plugin


def get_or_create_service(plugin_name: str) -> Optional[Service]:
    """按插件名惰性获取/创建 Service（同名已存在则复用）"""
    name = service_name_for(plugin_name)
    sv = _loaded_services.get(name)
    if sv:
        return sv
    try:
        sv = Service(name, help_=f"来自 NoneBot 插件 {plugin_name}")
    except AssertionError as e:
        logger.warning(f"插件 {plugin_name} 无法创建同名服务（{e}），跳过绑定")
        return None
    logger.info(f"为 NoneBot 插件创建 Service: {name} <- {plugin_name}")
    return sv


def bind_matcher(matcher: Type[Matcher], service: Optional[Service] = None) -> Optional[matcher_wrapper]:
    """把单个 nonebot matcher 绑定到 Service

    - 追加 check_service 规则：群事件按群开关生效，私聊放行
    - 注册进 _loaded_matchers：lssv 可见、enable/disable 可管、日志带模块名
    - 已绑定 / 无插件归属 / 无法归类的 matcher 返回 None
    """
    if matcher in _loaded_matchers:
        return _loaded_matchers[matcher]

    if service is None:
        plugin_name = getattr(matcher, "plugin_name", None)
        if not plugin_name:
            logger.warning(f"跳过无插件归属的 matcher: {matcher}")
            return None
        service = get_or_create_service(plugin_name)
        if service is None:
            return None

    matcher.rule = matcher.rule & service.check_service(only_group=False)
    mw = matcher_wrapper(service, matcher.type, matcher.priority)
    mw.load_matcher(matcher)
    _loaded_matchers[matcher] = mw
    service.matchers.append(str(mw))
    logger.info(f"绑定 matcher <lc>{mw}</> 到 Service {service.name}")
    return mw


def bind_plugin_matchers(plugin_names: Optional[Iterable[str]] = None) -> int:
    """绑定未绑定的 matcher，返回绑定数量（幂等，可重复调用）

    Args:
        plugin_names: 只绑定这些插件名的 matcher。为 None 时绑定
            load_nb_plugin 登记过的插件（推荐用法）。传入显式列表
            可覆盖登记列表，如补绑未登记的插件。
    """
    if plugin_names is None:
        plugin_names = _registered_plugins
    allowed = set(plugin_names) if plugin_names is not None else None
    count = 0
    for matcher in itertools.chain.from_iterable(nonebot.matcher.matchers.values()):
        if matcher in _loaded_matchers:
            continue
        if allowed is not None and getattr(matcher, "plugin_name", None) not in allowed:
            continue
        if bind_matcher(matcher):
            count += 1
    return count
