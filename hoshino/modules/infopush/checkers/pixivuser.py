from typing import List
import aiohttp
from hoshino import MessageSegment, Message

from hoshino.log import logger
from hoshino.sres import Res as R
from .._model import BaseInfoChecker, InfoData, Subscribe, checker


class PixivData(InfoData):
    user_id: str
    user_name: str
    urls: List[str]


@checker
class PixivUserChecker(BaseInfoChecker):
    seconds: int = 300
    name: str = "Pixiv投稿"
    distinguisher_name: str = "用户ID"

    @classmethod
    async def notice_format(cls, sub: Subscribe, data: PixivData):
        msg = MessageSegment.text(f"{sub.remark}更新了！\n")
        for url in data.urls:
            msg += await R.image_from_url(
                url.replace("i.pximg.net", "pixiv.shewinder.win"),
                anti_harmony=True,
            )
        return msg + MessageSegment.text(data.portal)

    @classmethod
    async def get_data(cls, url) -> PixivData:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url=url) as resp:
                    if resp.status == 200:
                        json_dic = await resp.json()
                        data = json_dic["illusts"][0]
                        v = PixivData()
                        v.pub_time = data["create_date"]
                        v.portal = f'https://www.pixiv.net/artworks/{data["id"]}'
                        v.user_id = data["user"]["id"]
                        v.user_name = data["user"]["name"]
                        urls: List[str] = []
                        if data["page_count"] == 1:
                            urls = [data["meta_single_page"]["original_image_url"]]
                        else:
                            urls = [
                                d["image_urls"]["original"] for d in data["meta_pages"]
                            ]
                        if len(urls) > 10:
                            urls = urls[:10]
                        v.urls = urls
                        return v
                    else:
                        logger.warning(f"访问{url}失败，status： {resp.status}")
                        return
            except Exception as e:
                logger.exception(e)
                return None

    @classmethod
    def form_url(cls, dinstinguisher: str) -> str:
        return f"https://api.shewinder.win/pixiv/user?user_id={dinstinguisher}"

    @classmethod
    def form_remark(cls, data: PixivData, distinguisher: str) -> str:
        return f"{data.user_name}的插画"
