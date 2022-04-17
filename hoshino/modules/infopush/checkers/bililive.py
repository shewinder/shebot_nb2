import aiohttp
import requests
from hoshino.log import logger
from hoshino.util import proxypool
from hoshino import MessageSegment

from .._config import Config
from .._exception import ProxyException, TimeoutException, NetworkException
from .._model import BaseInfoChecker, InfoData, SubscribeRecord

conf: Config.get_instance('infopush')


def get_name_from_room(room_id: str) -> str:
    headers = {
        "Referer": "https://link.bilibili.com/p/center/index",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36",
    }
    params = {"roomid": room_id}
    with requests.get(
        "https://api.live.bilibili.com/live_user/v1/UserInfo/get_anchor_in_room",
        headers=headers,
        params=params,
    ) as resp:
        if resp.status_code == 200:
            json_dic = resp.json()
            return json_dic["data"]["info"]["uname"]
        else:
            pass


class Live(InfoData):
    title: str
    cover: str


class BiliLiveChecker(BaseInfoChecker):
    async def notice_format(self, sub: SubscribeRecord, data: Live):
        return (
            f"{sub.remark}啦！\n{data.title}"
            + MessageSegment.image(data.cover)
            + data.portal
        )

    @classmethod
    async def get_name_from_room(cls, room_id: int) -> str:
        headers = {
            "Referer": "https://link.bilibili.com/p/center/index",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36",
        }
        params = {"roomid": room_id}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    "https://api.live.bilibili.com/live_user/v1/UserInfo/get_anchor_in_room",
                    headers=headers,
                    params=params,
                ) as resp:
                    if resp.status == 200:
                        json_dic = await resp.json()
                        return json_dic["data"]["info"]["uname"]
                    else:
                        logger.warning(f"未能成功获取主播名")
                        return "unknown"
            except Exception as e:
                logger.exception(e)
                return "unknown"

    @classmethod
    async def get_data(self, url) -> Live:
        headers = {
            "Referer": "https://link.bilibili.com/p/center/index",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36",
        }
        try:
            resp = await proxypool.aioget(url, headers=headers)
        except proxypool.TimeoutException:
            raise TimeoutException("get bilibili live data timeout")
        except proxypool.ProxyException:
            raise ProxyException("proxy unavailable")
        except proxypool.NetworkException:
            raise NetworkException("network unavailable")

        if resp.status == 200:
            json_dic = await resp.json()
            data = json_dic["data"]
            lv = Live()
            lv.pub_time = str(data["live_time"])
            lv.portal = f'https://live.bilibili.com/{data["room_id"]}'
            lv.title = data["title"]
            lv.cover = data["user_cover"]
            lv.is_new = True if data["live_status"] == 1 else False
            return lv
        else:
            raise ValueError(f"error: status{resp.status}")

    def form_url(self, dinstinguisher: str) -> str:
        return (
            "https://api.live.bilibili.com/room/v1/Room/get_info?room_id="
            + dinstinguisher
        )

    def form_remark(self, data: InfoData, distinguisher: str) -> str:
        name = get_name_from_room(distinguisher)
        return f"{name}B站直播间"


BiliLiveChecker(5, "Bilibili直播", "房间号")
