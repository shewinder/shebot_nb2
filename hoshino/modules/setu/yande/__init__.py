import random
from typing import TYPE_CHECKING, List, Tuple

from hoshino import Service, MessageEvent, Bot, T_State, MessageSegment, GroupMessageEvent, PrivateMessageEvent
from hoshino.sres import Res as R
from ..sync_tag import get_parser, get_translate
from .search import search_by_tag, search_yande
from hoshino.util.message_util import send_group_forward_msg
from hoshino.util import normalize_str

from .._model import Setu
from fuzzywuzzy import process

if TYPE_CHECKING:
    import re

sv = Service("yande")

search_with_author = sv.on_regex(r"^yande (.{1,40})$", only_group=False)

max_once = 2


@search_with_author.handle()
async def send_setu(bot: Bot, event: MessageEvent, state: T_State):
    match: re.Match = state["match"]
    tag_expr: str = match.group(1)
    tag_expr = tag_expr.replace("yande", "")

    if not tag_expr:
        return

    tags = tag_expr.split("+")


    sv.logger.info(f"search yande tags: {tags}")
    setus: List[Setu] = []

    async def get_setus_from_yande(tags: List[str]) -> Tuple[List[Setu], List[str]]:
        trans = get_translate()
        for k in list(trans.keys()):
            trans[normalize_str(k)] = trans[k]
        yande_tags = []
        for tag in tags:
            res = process.extractOne(tag, trans.keys(), score_cutoff=95)
            if res:
                t, score = tuple(res)
                sv.logger.info(
                    f"{tag} match yande tag {t}, score {score}, tranlated {trans[t]}"
                )
                yande_tags.append(trans[t])
            else:
                yande_tags.append(tag)
        if yande_tags:
            return await search_yande(yande_tags), yande_tags
        else:
            return [], []


    sv.logger.info("trying to translate to yande tag")
    setus, hit_tags = await get_setus_from_yande(tags)
    sv.logger.info(f"yande found {len(setus)}")

    if not setus:  # yande not found, try pixiv
        await bot.send(event, f"not found {tags} in yande")

    if len(setus) > max_once:
        setus = random.sample(setus, max_once)

    await bot.send(event, f'search tag: {",".join(hit_tags)}')
    msgs = []
    for setu in setus:
        try:
            sv.logger.info(f"downloading {setu.url}")
            msgs.append(MessageSegment.text(setu.tags))
            msgs.append(
                await R.image_from_url(setu.url, anti_harmony=True, timeout=30)
            )
            sv.logger.info(f"download finished")
        except Exception as e:
            sv.logger.error(f"{setu.url} url error: {e}")
    sv.logger.info(f"sending group forward msg...")
    if isinstance(event, GroupMessageEvent):
        await send_group_forward_msg(bot, event.group_id, msgs)
    else:
        await bot.send(event, msgs)
