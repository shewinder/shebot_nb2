import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple, Type, TypeVar, Union


from hoshino import Bot, Message, MessageSegment, get_bot_list
from hoshino.log import logger
from pydantic import BaseModel

from ._exception import NetworkException, ProxyException, TimeoutException
from ._data import SubscribeRecord, query_records

from hoshino.glob import _sub_data


def get_sub_data() -> Dict[str, List["Subscribe"]]:
    return _sub_data


# 这个函数是更换了存储介质的转换器， 所以很屎
def refresh_subdata():
    """
    刷新内存中的订阅数据
    """
    global _sub_data
    _sub_data.clear()
    subs: List[SubscribeRecord] = query_records()
    _dict: Dict[str, Subscribe] = {}
    for sub in subs:
        if sub.url in _dict:
            _dict[sub.url].creator[sub.group].append(sub.creator)
        else:
            _dict[sub.url] = Subscribe(
                url=sub.url,
                checker=sub.checker,
                remark=sub.remark,
                date=sub.date,
                creator={sub.group: [sub.creator]},
            )
    for sub_item in _dict.values():
        _sub_data[sub_item.checker].append(sub_item)


class Subscribe(BaseModel):
    checker: str
    remark: str
    url: str
    date: str
    creator: Dict[str, List[str]]  # {group_id: [user_id, ...]}

    def delete(self):
        SubscribeRecord.select().where(SubscribeRecord.url == self.url).delete()
        refresh_subdata()

    # def save(self):
    #     global sub_data
    #     if self in get_sub_data().get(self.checker, []):
    #         sub_data.save_to_file()
    #     else:
    #         get_sub_data()[self.checker].append(self)
    #         sub_data.save_to_file()


def get_creators() -> Dict[str, List[str]]:
    creators = defaultdict(list)
    for sub in get_sub_data():
        creators[sub.group].append(sub.creator)
    return creators


@dataclass
class InfoData:
    """
    插件的info数据类应该继承此类
    """

    pub_time: str = ""
    portal: str = ""
    is_new: bool = True  # 用于手动指定消息是否为新消息


_checkers: List[Type["BaseInfoChecker"]] = []


class BaseInfoChecker:
    """
    seconds: checker运行间隔秒数, 默认600s
    name: checker名称, 仅用作显示
    distinguisher_name: 用于checker使用的区分不同订阅， 如 id， user_name，用于提示用户输入
    """

    seconds: int = 600
    name: str = "unnamed checker"
    distinguisher_name: str = "id"

    @classmethod
    def get_all_checkers(cls) -> List["BaseInfoChecker"]:
        return _checkers

    @staticmethod
    def get_checker(name: str) -> "BaseInfoChecker":
        for checker in _checkers:
            if checker.__name__ == name:
                return checker
        raise ValueError(f"{name} not exist")

    @classmethod
    def get_subscribe(cls, url: str) -> Subscribe:
        """
        通过订阅的唯一标识即url获取SubscribeRecord对象
        """
        for sub in get_sub_data().get(cls.__name__, []):
            if sub.url == url:
                return sub
        return None

    @classmethod
    def get_creator_subs(
        cls, group_id: str, creator_id: Union[int, str]
    ) -> List[Subscribe]:
        group_id = str(group_id)
        creator_id = str(creator_id)
        subs = get_sub_data().get(cls.__name__, [])
        return list(
            filter(
                lambda x: group_id in x.creator and creator_id in x.creator[group_id],
                subs,
            )
        )

    @classmethod
    def delete_creator_sub(
        cls, group_id: int, creator_id: Union[int, str], sub: Subscribe
    ):
        group_id = str(group_id)
        creator_id = str(creator_id)
        if group_id in sub.creator and creator_id in sub.creator[group_id]:
            sub.creator[group_id].remove(creator_id)
            if len(sub.creator[group_id]) == 0:
                del sub.creator[group_id]
            if len(sub.creator) == 0:
                get_sub_data().get(cls.__name__).remove(sub)

    @classmethod
    def add_sub(
        cls,
        group_id: int,
        url: str,
        remark: str,
        creator_id: Union[int, str],
    ) -> Subscribe:
        SubscribeRecord.create(
            group=group_id,
            checker=cls.__name__,
            url=url,
            creator=creator_id,
            remark=remark,
            date="",
        )
        refresh_subdata()

    @classmethod
    async def notice_format(cls, sub: Subscribe, data: InfoData) -> Message:
        """
        默认的通知排版格式，子类可重写此函数
        """
        return Message(f"{sub.remark}更新啦！\n传送门{data.portal}")

    @classmethod
    async def notice(cls, sub: Subscribe, data: InfoData):
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
    async def check(cls, sub: Subscribe) -> Tuple[bool, InfoData]:
        try:
            data = await cls.get_data(sub.url)
        except TimeoutException as e:
            logger.warning(f"{e}")
            return False, None
        except ProxyException as e:
            logger.warning(f"{e}")
            return False, None
        except NetworkException as e:
            logger.warning(f"{e}")
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
            SubscribeRecord.update(date=curr_date).where(
                SubscribeRecord.url == sub.url
            ).execute()
            refresh_subdata()
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
