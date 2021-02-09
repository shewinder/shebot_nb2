'''
Author: AkiraXie
Date: 2021-01-28 00:44:32
LastEditors: AkiraXie
LastEditTime: 2021-02-10 00:21:01
Description: 
Github: http://github.com/AkiraXie/
'''
import asyncio
import re
import os
import json
from collections import defaultdict
from loguru import logger
from hoshino import Bot, service_dir as _service_dir, Message, MessageSegment
from hoshino.event import Event
from hoshino.matcher import Matcher, on_command, on_message,  on_startswith, on_endswith, on_notice, on_request, on_shell_command
from hoshino.permission import ADMIN, NORMAL, OWNER, Permission, SUPERUSER
from hoshino.util import get_bot_list
from hoshino.rule import ArgumentParser, Rule, to_me, regex, keyword
from hoshino.typing import Dict, Iterable, Optional, Union, T_State, Set, List, Type

_illegal_char = re.compile(r'[\\/:*?"<>|\.!！]')
_loaded_services: Dict[str, "Service"] = {}


def _save_service_data(service: 'Service'):
    data_file = os.path.join(_service_dir, f'{service.name}.json')
    with open(data_file, 'w', encoding='utf8') as f:
        json.dump({
            "name": service.name,
            "enable_group": list(service.enable_group),
            "disable_group": list(service.disable_group)
        }, f, ensure_ascii=False, indent=2)


def _load_service_data(service_name: str) -> dict:
    data_file = os.path.join(_service_dir, f'{service_name}.json')
    if not os.path.exists(data_file):
        return {}
    with open(data_file, encoding='utf8') as f:
        data = json.load(f)
        return data


class Service:
    def __init__(self, name: str, manage_perm: Permission = ADMIN, enable_on_default: bool = True, visible: bool = True):
        '''
        Descrption:  定义一个服务

        Params: 

        *`name` : 服务名字

        *`manage_perm` : 管理服务的权限,是一`Permission`实例,`ADMIN`和`OWNER`和`SUPERSUSER`是允许的

        *`enable_on_default` : 默认开启状态

        *`visible` : 默认可见状态
        '''
        assert not _illegal_char.search(
            name) or not name.isdigit(), 'Service name cannot contain character in [\\/:*?"<>|.] or be pure number'
        assert manage_perm in (
            ADMIN, OWNER, SUPERUSER), 'Service manage_perm is illegal'
        self.name = name
        self.manage_perm = manage_perm
        self.enable_on_default = enable_on_default
        self.visible = visible
        assert self.name not in _loaded_services, f'Service name "{self.name}" already exist!'
        _loaded_services[self.name] = self
        data = _load_service_data(self.name)
        self.enable_group = set(data.get('enable_group', []))
        self.disable_group = set(data.get('disable_group', []))

    @staticmethod
    def get_loaded_services() -> Dict[str, "Service"]:
        return _loaded_services

    def set_enable(self, group_id):
        self.enable_group.add(group_id)
        self.disable_group.discard(group_id)
        _save_service_data(self)

    def set_disable(self, group_id):
        self.enable_group.discard(group_id)
        self.disable_group.add(group_id)
        _save_service_data(self)

    async def get_enable_groups(self) -> Dict[int, List]:
        gl = defaultdict(list)
        for sid, bot in get_bot_list():
            sid = int(sid)
            sgl = set(g['group_id'] for g in await bot.get_group_list(self_id=sid))
            if self.enable_on_default:
                sgl = sgl - self.disable_group
            else:
                sgl = sgl & self.enable_group
            for g in sgl:
                gl[g].append((sid, bot))
        return gl

    def check_enabled(self, group_id: int) -> bool:
        return bool((group_id in self.enable_group) or (
            self.enable_on_default and group_id not in self.disable_group))

    def check_service(self, only_to_me: bool = False, only_group: bool = True) -> Rule:
        async def _cs(bot: Bot, event: Event, state: T_State) -> bool:
            if not 'group_id' in event.__dict__:
                return not only_group
            else:
                group_id = event.group_id
                return self.check_enabled(group_id)
        rule = Rule(_cs)
        if only_to_me:
            rule = rule & (to_me())
        return rule

    def on_command(self, name: str, only_to_me: bool = False, aliases: Optional[Iterable] = None, only_group: bool = True, permission: Permission = NORMAL, **kwargs) -> Type[Matcher]:
        if isinstance(aliases, str):
            aliases = set(aliases,)
        else:
            aliases = set(aliases) if aliases is not None else set()
        kwargs['aliases'] = aliases
        kwargs['permission'] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs['rule'] = rule
        return on_command(name, **kwargs)

    def on_shell_command(self, name: str, only_to_me: bool = False, aliases: Optional[Iterable] = None, parser: Optional[ArgumentParser] = None, only_group: bool = True, permission: Permission = NORMAL, **kwargs) -> Type[Matcher]:
        if isinstance(aliases, str):
            aliases = set(aliases,)
        else:
            aliases = set(aliases) if aliases else set()
        kwargs['parser'] = parser
        kwargs['aliases'] = aliases
        kwargs['permission'] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs['rule'] = rule
        return on_shell_command(name, **kwargs)

    def on_startswith(self, msg: str, only_to_me: bool = False, only_group: bool = True, permission: Permission = NORMAL, **kwargs) -> Type[Matcher]:
        kwargs['permission'] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs['rule'] = rule
        return on_startswith(msg, **kwargs)

    def on_endswith(self, msg: str, only_to_me: bool = False, only_group: bool = True, permission: Permission = NORMAL, **kwargs) -> Type[Matcher]:
        kwargs['permission'] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs['rule'] = rule
        return on_endswith(msg, **kwargs)

    def on_keyword(self, keywords: Union[Set[str], str], normal: bool = True, only_to_me: bool = False, only_group: bool = True, permission: Permission = NORMAL, **kwargs) -> Type[Matcher]:
        if isinstance(keywords, str):
            keywords = set(keywords,)
        else:
            keywords = set(keywords) if keywords is not None else set()
        kwargs['permission'] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs['rule'] = keyword(keywords, normal) & rule
        return on_message(**kwargs)

    def on_regex(self, pattern: str, flags: Union[int, re.RegexFlag] = 0, normal: bool = True, only_to_me: bool = False, only_group: bool = True, permission: Permission = NORMAL, **kwargs) -> Type[Matcher]:
        '''
        根据正则表达式进行匹配。
        可以通过 ``state["_matched"]`` 获取正则表达式匹配成功的文本。
        可以通过 ``state["match"]`` 获取正则表达式匹配成功后的`match`
        '''
        rule = self.check_service(only_to_me, only_group)
        rule = regex(pattern, flags, normal) & rule
        return on_message(rule, permission, **kwargs)

    def on_message(self,  only_to_me: bool = False, only_group: bool = True, permission: Permission = NORMAL, **kwargs) -> Type[Matcher]:
        kwargs['permission'] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs['rule'] = rule
        return on_message(**kwargs)

    def on_notice(self,  only_group: bool = True, **kwargs) -> Type[Matcher]:
        rule = self.check_service(0, only_group)
        return on_notice(rule, **kwargs)

    def on_request(self, only_group: bool = True, **kwargs) -> Type[Matcher]:
        rule = self.check_service(0, only_group)
        return on_request(rule, **kwargs)

    async def broadcast(self, msgs: Optional[Iterable], tag='', interval_time=0.5):
        if isinstance(msgs, (str, Message, MessageSegment)):
            msgs = (msgs,)
        gdict = await self.get_enable_groups()
        for gid in gdict.keys():
            for sid, bot in gdict[gid]:
                for msg in msgs:
                    await asyncio.sleep(interval_time)
                    try:
                        await bot.send_group_msg(self_id=sid, group_id=gid, message=msg)
                    except Exception as e:
                        logger.exception(e)
                        logger.error(
                            f"{self.name}: {sid}在群{gid}投递{tag}失败, {type(e)}")
                    logger.info(f"{self.name}: {sid}在群{gid}投递{tag}成功")
