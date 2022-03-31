import asyncio
from dataclasses import dataclass
from typing import Dict, List, Union

from hoshino import Message, MessageSegment
from pydantic import BaseModel

from hoshino import get_bot_list, Bot, userdata_dir, MessageSegment
from hoshino.log import logger
from ._glob import CHECKERS, SUBS
from hoshino.util.sutil import load_config, save_config
from ._exception import TimeoutException, ProxyException, NetworkException


plug_dir = userdata_dir.joinpath("infopush")
if not plug_dir.exists():
    plug_dir.mkdir()

json_filepath = plug_dir.joinpath("subscribe.json")
if not json_filepath.exists():
    json_filepath.touch()


class SubscribeRecord(BaseModel):
    checker: str
    remark: str
    url: str
    date: str
    creator: Dict[int, List[str]] # {group_id: [user_id, ...]}

    @classmethod
    def to_json(cls):
        return {k: {i: j.dict() for i, j in v.items()} for k, v in SUBS.items()}

    @classmethod
    def init(cls):
        """
        导入保存的订阅到SUBS全局变量
        """
        dic = load_config(json_filepath)
        for k, v in dic.items():
            SUBS[k] = {i: SubscribeRecord(**j) for i, j in v.items()}

    def save(self):
        if len(self.creator) == 0:
            logger.warning("订阅者为空")
            return
        SUBS[self.checker][self.url] = self
        save_config(self.to_json(), json_filepath)

    def delete(self):
        sub = SUBS.get(self.checker, {}).get(self.url)
        if sub:
            del SUBS[self.checker][self.url]
            save_config(self.to_json(), json_filepath)
        else:
            raise ValueError("不存在该记录")


@dataclass
class InfoData:
    """
    插件的info数据类应该继承此类
    """

    pub_time: str = None
    portal: str = None
    is_new: bool = True  # 用于手动指定消息是否为新消息


class BaseInfoChecker:
    def __init__(
        self,
        seconds: int = 600,
        name: str = "unnamed checker",
        distinguisher_name: str = "id",
    ) -> None:
        """
        seconds 代表checker运行间隔秒数, 默认120s
        """
        self.seconds = seconds
        self.name = name
        self.distinguisher_name = distinguisher_name
        assert self not in CHECKERS, f"{self.name}已存在"
        CHECKERS.append(self)

    @staticmethod
    def get_all_checkers() -> List["BaseInfoChecker"]:
        return CHECKERS

    @staticmethod
    def get_subscribe(checker_name: str, url: str) -> SubscribeRecord:
        return SUBS.get(checker_name, dict()).get(url, dict())

    @classmethod
    async def get_data(cls, url: str = None) -> InfoData:
        # 获取数据,插件应实现此方法
        raise NotImplementedError

    @classmethod
    def get_creator_subs(
        cls, group_id: int, creator_id: Union[int, str]
    ) -> List[SubscribeRecord]:
        if isinstance(creator_id, int):
            creator_id = str(creator_id)
        _subs = []
        v: Dict[str, SubscribeRecord] = SUBS.get(cls.__name__, {})
        for vv in v.values():
            if group_id in vv.creator and creator_id in vv.creator[group_id]:
                _subs.append(vv)
        return _subs

    @classmethod
    def delete_creator_sub(
        cls, group_id: int, creator_id: Union[int, str], sub: SubscribeRecord
    ):
        if isinstance(creator_id, int):
            creator_id = str(creator_id)
        if group_id in sub.creator and creator_id in sub.creator[group_id]:
            sub.creator[group_id].remove(creator_id)
            if len(sub.creator[group_id]) == 0:
                del sub.creator[group_id]
            if len(sub.creator) == 0:
                sub.delete()
            sub.save()
        else:
            pass

    @classmethod
    def add_sub(
        cls,
        group_id: int,
        url: str,
        remark: str = None,
        creator_id: Union[int, str] = None,
    ):
        if isinstance(creator_id, int):
            creator_id = str(creator_id)
        sub = cls.get_subscribe(cls.__name__, url)
        if sub:
            if group_id in sub.creator:
                if creator_id in sub.creator[group_id]:
                    raise ValueError("重复订阅")
                else:
                    sub.creator[group_id].append(creator_id)
            sub.creator[group_id] = [creator_id]
            sub.save()
        else:
            try:
                sub = SubscribeRecord(
                    checker=cls.__name__,
                    url=url,
                    remark=remark,
                    groups=[group_id],
                    users=[],
                    date="",
                    creator={group_id: [creator_id]},
                )
                sub.save()
                return sub
            except Exception as e:
                logger.exception(e)
                raise ValueError(e)

    @classmethod
    async def notice_format(cls, sub: SubscribeRecord, data: InfoData) -> Message:
        """
        默认的通知排版格式，子类可重写此函数
        """
        return Message(f"{sub.remark}更新啦！\n传送门{data.portal}")

    async def notice(self, sub: SubscribeRecord, data: InfoData):
        bot: Bot = get_bot_list()[0]
        for gid in sub.creator:
            try:
                creators = sub.creator[gid]
                msg = [MessageSegment.at(uid) for uid in creators]
                msg.append(MessageSegment.text("\n"))
                fmt = await self.notice_format(sub, data)
                msg.extend(fmt)
                await bot.send_group_msg(group_id=gid, message=msg)
            except Exception as e:
                logger.exception(e)
            await asyncio.sleep(0.5)

    async def check_and_notice(self, sub: SubscribeRecord):
        try:
            data = await self.get_data(sub.url)
        except TimeoutException as e:
            logger.warning(f'{e}')
            return False
        except ProxyException as e:
            logger.warning(f'{e}')
            return False
        except NetworkException as e:
            logger.warning(f'{e}')
            return False
        except Exception as e:
            logger.exception(e)
            return False
        if not data:
            logger.warning(f"检查{sub.checker}出错")
            return
        curr_date = data.pub_time
        if sub.date != curr_date and data.is_new:
            logger.info(f"检测到{sub.remark}更新")
            sub.date = curr_date
            sub.save()
            await self.notice(sub, data)
            return True
        else:
            return False

    def form_url(self, dinstinguisher: str) -> str:
        """
        根据唯一标识生成url, checker应实现此方法
        """
        raise NotImplementedError

    def form_remark(self, data: InfoData, distinguisher: str) -> str:
        """
        根据data生成remark, checker应实现此方法
        """
        raise NotImplementedError


