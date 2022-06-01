from hoshino.util import proxypool
from hoshino import MessageSegment

from .._config import Config
from .._exception import ProxyException, TimeoutException
from .._model import BaseInfoChecker, InfoData, Subscribe, checker

conf: Config.get_instance('infopush')

class DouyuLive(InfoData):
    title: str
    cover: str
    name: str


@checker
class DouyuLiveChecker(BaseInfoChecker):
    
    seconds: int = 5
    name: str = '斗鱼直播'
    distinguisher_name: str = "房间号"

    @classmethod
    def notice_format(cls, sub: Subscribe, data: DouyuLive):
        return (
            f"{sub.remark}啦！\n{data.title}"
            + MessageSegment.image(data.cover)
            + data.portal
        )

    @classmethod
    async def get_name_from_room(cls, room_id):
        data = await cls.get_data(f"http://open.douyucdn.cn/api/RoomApi/room/{room_id}")
        return data.name

    @classmethod
    async def get_data(self, url) -> DouyuLive:
        headers = {
            "Referer": f'https://www.douyu.com/{url.split("/")[-1]}',
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36",
        }
        try:
            resp = await proxypool.aioget(url, headers=headers)
        except proxypool.TimeoutException:
            raise TimeoutException("get douyu live data timeout")
        except proxypool.ProxyException:
            raise ProxyException("proxy unavailable")
        except:
            raise
        if resp.status == 200:
            json_dic = await resp.json()
            data = json_dic["data"]
            lv = DouyuLive()
            lv.pub_time = str(data["start_time"])
            lv.portal = f'https://douyu.com/{data["room_id"]}'
            lv.title = data["room_name"]
            lv.cover = data["room_thumb"]
            lv.name = data["owner_name"]
            lv.is_new = (
                True if data["room_status"] == "1" else False
            )  # 用于判断是否正在开播, 防止订阅时推送历史开播信息
            return lv
        else:
            raise ValueError(f"error: status{resp.status}")

    @classmethod
    def form_url(cls, dinstinguisher: str) -> str:
        return f"http://open.douyucdn.cn/api/RoomApi/room/" + dinstinguisher

    @classmethod
    def form_remark(cls, data: DouyuLive, distinguisher: str) -> str:
        return f"{data.name}直播"



