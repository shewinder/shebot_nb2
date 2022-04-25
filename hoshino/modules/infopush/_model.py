import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple, Type, TypeVar, Union

from hoshino import Bot, Message, MessageSegment, get_bot_list, userdata_dir
from hoshino.log import logger
from hoshino.util.persist import Persistent
from pydantic import BaseModel

from ._exception import NetworkException, ProxyException, TimeoutException

T = TypeVar('T')

plug_dir = userdata_dir.joinpath("infopush")
if not plug_dir.exists():
    plug_dir.mkdir()

json_filepath = plug_dir.joinpath("sub.json")
if not json_filepath.exists():
    json_filepath.touch()



class SubscribeRecord(BaseModel):
    checker: str
    remark: str
    url: str
    date: str
    creator: Dict[str, List[str]] # {group_id: [user_id, ...]}

    def delete(self):
        global sub_data
        sub_data.data.get(self.checker).remove(self)

    def save(self):
        global sub_data
        if self in sub_data.data.get(self.checker, []):
            sub_data.save_to_file()
        else:
            sub_data.data[self.checker].append(self)
            sub_data.save_to_file()

class SubscribeData(Persistent):
    data: Dict[str, List["SubscribeRecord"]] = defaultdict(list) # {checker_name: [SubscribeRecord ...]}

sub_data = SubscribeData(json_filepath)

@dataclass
class InfoData:
    """
    插件的info数据类应该继承此类
    """

    pub_time: str = ''
    portal: str = ''
    is_new: bool = True  # 用于手动指定消息是否为新消息

_checkers: List[Type['BaseInfoChecker']] = []

class BaseInfoChecker:
    """
    seconds: checker运行间隔秒数, 默认600s
    distinguisher_name: 用于checker使用的区分不同订阅， 如 id， user_name，用于提示用户输入
    """
    seconds: int = 600
    name: str = 'unnamed checker'
    distinguisher_name: str = "id"

    @classmethod
    def get_all_checkers(cls) -> List["BaseInfoChecker"]:
        return _checkers

    @staticmethod
    def get_checker(name: str) -> "BaseInfoChecker":
        for checker in _checkers:
            if checker.__name__ == name:
                return checker
        raise ValueError(f'{name} not exist')

    @classmethod
    def get_subscribe(cls, url: str) -> SubscribeRecord:
        """
        通过订阅的唯一标识即url获取SubscribeRecord对象
        """
        for sub in sub_data.data.get(cls.__name__, []):
            if sub.url == url:
                return sub
        return None

    @classmethod
    def get_creator_subs(
        cls, group_id: str, creator_id: Union[int, str]
    ) -> List[SubscribeRecord]:
        group_id = str(group_id)
        creator_id = str(creator_id)
        subs = sub_data.data.get(cls.__name__, [])
        return list(filter(lambda x: group_id in x.creator and creator_id in x.creator[group_id], subs))

    @classmethod
    def delete_creator_sub(
        cls, group_id: int, creator_id: Union[int, str], sub: SubscribeRecord
    ):
        group_id = str(group_id)
        creator_id = str(creator_id)
        if group_id in sub.creator and creator_id in sub.creator[group_id]:
            sub.creator[group_id].remove(creator_id)
            if len(sub.creator[group_id]) == 0:
                del sub.creator[group_id]
            if len(sub.creator) == 0:
                sub_data.data.get(cls.__name__).remove(sub)

    @classmethod
    def add_sub(
        cls,
        group_id: int,
        url: str,
        remark: str = None,
        creator_id: Union[int, str] = None,
    ) -> SubscribeRecord:
        group_id = str(group_id)
        creator_id = str(creator_id)
        sub = cls.get_subscribe(url)
        if sub:
            if group_id in sub.creator:
                if creator_id in sub.creator[group_id]:
                    raise ValueError("重复订阅")
                else:
                    sub.creator[group_id].append(creator_id)
                    sub.save()
            else:
                sub.creator[group_id] = [creator_id]
        else:
            sub = SubscribeRecord(
                checker=cls.__name__,
                url=url,
                remark=remark,
                date="",
                creator={group_id: [creator_id]},
            )
            sub_data.data[cls.__name__].append(sub)
        return sub


    @classmethod
    async def notice_format(cls, sub: SubscribeRecord, data: InfoData) -> Message:
        """
        默认的通知排版格式，子类可重写此函数
        """
        return Message(f"{sub.remark}更新啦！\n传送门{data.portal}")

    @classmethod
    async def notice(cls, sub: SubscribeRecord, data: InfoData):
        bot: Bot = get_bot_list()[0]
        for gid in sub.creator:
            try:
                creators = sub.creator[gid]
                msg = [MessageSegment.at(uid) for uid in creators]
                msg.append(MessageSegment.text("\n"))
                fmt = await cls.notice_format(sub, data)
                msg.extend(fmt)
                await bot.send_group_msg(group_id=gid, message=msg)
            except Exception as e:
                logger.exception(e)
            await asyncio.sleep(0.5)

    @classmethod
    async def check(cls, sub: SubscribeRecord) -> Tuple[bool, InfoData]:
        try:
            data = await cls.get_data(sub.url)
        except TimeoutException as e:
            logger.warning(f'{e}')
            return False, None
        except ProxyException as e:
            logger.warning(f'{e}')
            return False, None
        except NetworkException as e:
            logger.warning(f'{e}')
            return False, None
        except Exception as e:
            raise
        if not data:
            logger.warning(f"检查{sub.checker}出错")
            return False, None
        curr_date = data.pub_time
        if sub.date != curr_date and data.is_new:
            logger.info(f"检测到{sub.remark}更新")
            sub.date = curr_date
            sub_data.save_to_file()
            return True, data
        else:
            return False, data

    @classmethod
    async def get_data(cls, url: str = None) -> InfoData:
        # 获取数据,插件应实现此方法
        raise NotImplementedError

    @classmethod
    def form_url(self, dinstinguisher: str) -> str:
        """
        根据唯一标识生成url, checker应实现此方法
        """
        raise NotImplementedError

    @classmethod
    def form_remark(self, data: InfoData, distinguisher: str) -> str:
        """
        根据data生成remark, checker应实现此方法
        """
        raise NotImplementedError

def checker(cls):
    """
    装饰器，将Checker添加至_checker全局变量
    """
    _checkers.append(cls)
    return cls


