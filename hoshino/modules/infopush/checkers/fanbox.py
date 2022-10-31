from io import BytesIO
import mimetypes
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List
import zipfile

from hoshino import  MessageSegment
import hoshino
from hoshino.log import logger
from hoshino.sres import Res as R
from hoshino.util import aiohttpx

from .._config import Config
from .._model import BaseInfoChecker, InfoData, Subscribe

conf = Config.get_instance("infopush")


class FanboxData(InfoData):
    user_id: str
    user_name: str
    title: str
    id: str


class FanboxChecker(BaseInfoChecker):
    seconds: int = 10
    name: str = "Pixiv投稿"
    distinguisher_name: str = "用户ID"

    @staticmethod
    async def get_post(post_id: int, cookie: str = None):
        params = {"postId": post_id}
        if not cookie:
            headers = {"Origin": "https://www.fanbox.cc"}
        else:
            headers = {
                "Origin": "https://www.fanbox.cc",
                "Cookie": f"FANBOXSESSID={cookie}",
            }
        resp = await aiohttpx.get(
            f"https://api.fanbox.cc/post.info", params=params, headers=headers
        )
        return resp.json

    @staticmethod
    async def handle_file(
        sub: Subscribe, url: str, extension: str, cookie: str = None
    ) -> List[MessageSegment]:
        url = url.replace("downloads.fanbox.cc", "fanbox.shewinder.win")
        if not cookie:
            headers = {"Origin": "https://www.fanbox.cc"}
        else:
            headers = {
                "Origin": "https://www.fanbox.cc",
                "Cookie": f"FANBOXSESSID={cookie}",
            }
        res = []
        if extension == "zip":
            resp = await aiohttpx.get(url, headers=headers)
            zf = zipfile.ZipFile(BytesIO(resp.content))
            with TemporaryDirectory() as tmp_dir:
                zf.extractall(tmp_dir)
                for root, dirs, files in os.walk(tmp_dir):
                    for file in files:
                        p = Path(root).joinpath(file)
                        if mimetypes.guess_type(p)[0].startswith("image"):
                            logger.info(f"find image {file} in zip file")
                            res.append(R.image(p, anti_harmony=True))
        elif extension in ["mp4"]:
            logger.info("this post is video")
            bot = hoshino.get_bot_list()[0]

            filename = f'{url.split("/")[-1]}'
            v = await bot.call_api(
                "download_file",
                url=url,
                headers=[f"{k}={v}" for k, v in headers.items()],
            )
            for gid in sub.creator.keys():
                try:
                    await bot.call_api(
                        "upload_group_file",
                        group_id=gid,
                        file=v["file"],
                        name="test" + filename,
                    )
                except Exception as e:
                    res.append(MessageSegment.text('视频上传失败'))
        return res

    @classmethod
    async def notice_format(cls, sub: Subscribe, data: FanboxData):
        msg = MessageSegment.text(f"{sub.remark}更新了！\n") + ""
        post_id = data.id
        cookies = conf.fanbox_cookies.values()
        if not cookies:
            j = await FanboxChecker.get_post(post_id)
            d: dict = j["body"]
            if d.get("body"):
                logger.info("the post can be accessed")
                if d["type"] == "image":
                    for im in d["body"]["images"]:
                        msg += await R.image_from_url(
                            im["originalUrl"], anti_harmony=True
                        )
                    return msg + MessageSegment.text(data.portal)
                elif d["type"] == "file":
                    for file in d["body"]["files"]:
                        img_list = await FanboxChecker.handle_file(
                            sub, file["url"], file["extension"]
                        )
                        msg.extend(img_list)
            else:
                return (
                    msg
                    + (await R.image_from_url(d["imageForShare"], anti_harmony=True))
                    + MessageSegment.text(data.portal)
                )
        else:
            for ck in cookies:
                logger.info(f"using cookie {ck}")
                j = await FanboxChecker.get_post(post_id, ck)
                d: dict = j["body"]
                if d.get("body"):
                    headers = {
                        "Origin": "https://www.fanbox.cc",
                        "Cookie": f"FANBOXSESSID={ck}",
                    }
                    logger.info("the post can be accessed")
                    if d["type"] == "image":
                        logger.info("the type is image")
                        for im in d["body"]["images"]:
                            url = im["originalUrl"]
                            resp = await aiohttpx.get(url, headers=headers)
                            pic_bytes = resp.content
                            msg += R.image_from_memory(pic_bytes)
                    elif d["type"] == "file":
                        logger.info("the type is file")
                        for file in d["body"]["files"]:
                            logger.info(f'download url is {file["url"]}')
                            img_list = await FanboxChecker.handle_file(
                                sub, file["url"], file["extension"], ck
                            )
                            msg.extend(img_list)
                    return msg + MessageSegment.text(data.portal)
            return (
                msg
                + (await R.image_from_url(d["imageForShare"], anti_harmony=True))
                + MessageSegment.text(data.portal)
            )

    @classmethod
    async def get_data(cls, url) -> FanboxData:
        resp = await aiohttpx.get(url, headers={"Origin": "https://www.fanbox.cc"})
        if resp.status_code != 200:
            raise ValueError(resp.json)
        j = resp.json
        data = j["body"]["items"][0]
        f = FanboxData()
        f.pub_time = data["updatedDatetime"]
        f.id = data["id"]
        f.user_name = data["user"]["name"]
        f.user_id = data["user"]["userId"]
        f.portal = f'https://{data["creatorId"]}.fanbox.cc/posts/{data["id"]}'
        return f

    @classmethod
    def form_url(cls, dinstinguisher: str) -> str:
        return f"https://api.fanbox.cc/post.listCreator?creatorId={dinstinguisher}&limit=50"

    @classmethod
    def form_remark(cls, data: FanboxData, distinguisher: str) -> str:
        return f"{data.user_name}的fanbox"
