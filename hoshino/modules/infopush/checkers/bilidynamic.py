from typing import Dict, List, Union

import aiohttp
from pydantic import BaseModel, ValidationError
from nonebot.adapters.cqhttp.message import MessageSegment, Message

from hoshino.log import logger
from hoshino.sres import Res as R
from .._model import BaseInfoChecker, InfoData, SubscribeRecord

class Dynamic(InfoData):
    content: str
    imgs: List[str] = []

class BiliDynamicChecker(BaseInfoChecker):
    def notice_format(self, sub: SubscribeRecord , data: Dynamic):
        imgs = [MessageSegment.image(img) for img in data.imgs]
        msg = Message(f'{sub.remark}更新啦！\n{data.content}') \
              .extend(imgs) \
              .append(MessageSegment.text('\n' + data.portal))
        return msg
    
    @classmethod
    async def get_data(cls, url: str) -> Dynamic:
        def _get_uname_cont_and_imgs(card: str):
            try:
                c = VideoCard.parse_raw(card)
                return c.owner["name"], f'标题：\n{c.title}\n视频简介{c.desc}', [c.pic]
            except ValidationError:
                #print(card)
                pass
            try:
                c = PictureCard.parse_raw(card)
                return c.user["name"], c.item.description, [img["img_src"] for img in c.item.pictures]
            except ValidationError:
                pass
            try:
                c = ArticleCard.parse_raw(card)
                return c.author["name"], c.summary, c.image_urls
            except ValidationError:
                pass
            try:
                c = ForwardCard.parse_raw(card)
                ori_uname, _, imgs= _get_uname_cont_and_imgs(c.origin)
                content =  c.item.content + f'\n\n转发{ori_uname}的动态\n\n'
                content += _
                return c.user["uname"], content, imgs                 
            except ValidationError:
                c = TextCard.parse_raw(card) 
                return c.user["uname"], c.item.content, []
            except:
                print(card)

        headers = {
            'Referer': f'https://space.bilibili.com/${url.split("=")[1]}/',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36'
        }
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.get(url=url, 
                                       headers=headers) as resp:
                    if resp.status == 200:
                        json_dic = await resp.json()
                        data = json_dic['data']['cards'][0]
                        try:
                            c = RootCard(**data)
                        except:
                            logger.error(str(data))
                            print(data)
                        dyc = Dynamic()
                        dyc.pub_time = str(c.desc.timestamp)
                        dyc.portal = f'https://space.bilibili.com/{c.desc.uid}/dynamic'
                        try:
                            _, dyc.content, dyc.imgs = _get_uname_cont_and_imgs(c.card)
                            return dyc
                        except Exception as e:
                            logger.exception(e)
                            dyc.is_new = False
                            return dyc
                    else:
                        logger.warning(f'访问{url}失败，status： {resp.status}')
                        return
            except Exception as e:
                logger.exception(e)
                return None

BiliDynamicChecker(60)

class Desc(BaseModel):
    uid: int 
    type: int
    rid: int
    dynamic_id: int
    timestamp: int
    uid_type: int
    status: int

class TextItem(BaseModel):
    content: str

class PictureItem(BaseModel):
    description: str
    pictures: List

class ForwardItem(BaseModel):
    content: str

class TextCard(BaseModel):
    user: Dict
    item: TextItem

class PictureCard(BaseModel):
    user: Dict
    item: PictureItem

class VideoCard(BaseModel):
    owner: Dict
    aid: int
    title: str
    pic: str
    desc: str

class ArticleCard(BaseModel):
    author: Dict
    act_id: int
    summary: str
    image_urls: List

class ForwardCard(BaseModel):
    user: Dict
    item: ForwardItem
    origin: str

class RootCard(BaseModel):
    desc: Desc
    card: str