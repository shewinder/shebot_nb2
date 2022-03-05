from typing import Any, Dict, Iterable, List, Optional, Tuple, Union, Callable
from hoshino.log import logger
from hoshino.typing import GroupMessageEvent
from datetime import datetime, timedelta
from collections import defaultdict
from hoshino import Bot, get_bot_list

_allsession: Dict[Tuple[int, str], "ActSession"] = {}
_allaction = defaultdict(dict)
_allhandlers: Dict[str, List[Callable]] = defaultdict(list)

class SessionFinishedException(Exception):
    pass
class SessionExistException(Exception):
    pass

class ActSession:
    def __init__(self, name: str, group_id: int, creator: int, max_user: int=10, expire_time: int=120, usernum_limit: bool=False):
        self.name = name
        self.group_id = group_id #session所在群聊
        self.creator = creator #session的创建者
        self.users = list([creator])
        self.max_user = max_user
        self.usernum_limit = usernum_limit
        self.expire_time = expire_time
        self.create_time = datetime.now()
        self._state = {} 

    def __getattr__(self, item) -> Any:
        return self.state.get(item)
 
    @property
    def state(self):
        """
        State of the session.
        This contains all named arguments and
        other session scope temporary values.
        """
        return self._state
    
    @property
    def actions(self):
        """
        Actions of the session.
        This dict contains all actions which
        can be triggered by certain word
        """
        return _allaction.get(self.name) or {}

    def handlers(self) -> List[Callable]:
        return _allhandlers.get(self.name) or []

    @classmethod
    def from_event(cls, name: str, event: GroupMessageEvent, max_user: int=100, expire_time: int=300, usernum_limit: bool=False):
        return cls(name, event.group_id, event.user_id, max_user, expire_time, usernum_limit)

    def count_user(self) -> int:
        return len(self.users)

    def add_user(self, uid: int):
        #this function should cautiously be used 
        #because it can not assure user add only one session in the same group
        #better to use join_session in InteractHandler  
        if len(self.users) >= self.max_user:
            raise ValueError('人数超过限制,无法加入')
        self.users.append(uid)

    def close(self):
        InteractHandler().close_session(self.group_id, self.name)
        logger.info(f'interaction session {self.name} has been closed')

    def is_expire(self) -> bool:
        now = datetime.now()
        return self.create_time + timedelta(seconds=self.expire_time) < now

    async def send(self, event: GroupMessageEvent, message: str):
        bot: Bot = get_bot_list()[0]
        await bot.send(event, message)

    async def finish(self, event: GroupMessageEvent, message: str):
        self.close()
        await self.send(event, message)
        raise SessionFinishedException('session has finished')

    
class InteractHandler:
    def __init__(self) -> None:
        self.allsession = {}
        global _allaction
        global _allsession
        self.allsession = _allsession
        self.allaction = _allaction

    def create_session(self, session: ActSession):
        gid = session.group_id
        name = session.name
        if (gid, name) in self.allsession: 
            raise SessionExistException('session already exist')
        self.allsession[(gid, name)] = session

    @staticmethod
    def close_session(group_id: int, name: str):
        global _allsession
        if (group_id, name) in _allsession:
            del _allsession[(group_id, name)]

    def find_session(self, gid: int, name: str) -> ActSession:
            return self.allsession.get((gid, name))

    def find_session_by_event(self, event: GroupMessageEvent) -> ActSession:
        gid = event.group_id
        uid = event.user_id
        for k in self.allsession:
            if gid == k[0]:
                if not self.allsession[k].usernum_limit or uid in self.allsession[k].users:
                    return self.allsession[k]
        return None
    
    def add_action(self, name: str, trigger_word: Union[str, Iterable]):
        """
        用作装饰器
        """
        if isinstance(trigger_word, str):
            trigger_word = (trigger_word,)
        else:
            trigger_word = set(trigger_word) # 去重
        def deco(func: Callable) -> Callable:
            for tw in trigger_word:
                if tw in self.allaction[name]:
                    raise ValueError('action trigger word duplication')
                self.allaction[name][tw] = func
        return deco

    def add_handler(self, session_name: str):
        """
        用作装饰器
        """
        def deco(func: Callable) -> Callable:
            if session_name in _allhandlers:
                _allhandlers[session_name].append(func)
            else:
                _allhandlers[session_name] = [func]
        return deco

    def join_session(self, event: GroupMessageEvent, session: ActSession):
        exist = self.find_session_by_event(event)
        if exist: #user已经在此session或者其它session中
            raise ValueError(f'已经在{exist.name}中，无法再次加入或者加入其它互动')
        session.add_user(event.user_id)

interact = InteractHandler()