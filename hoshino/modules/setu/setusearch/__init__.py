import random
from typing import TYPE_CHECKING, List, Tuple

from hoshino import Service, GroupMessageEvent, Bot, T_State, MessageSegment
from hoshino.sres import Res as R
from ..sync_tag import get_parser, get_translate
from .search import search_by_tag, search_yande
from hoshino.util.message_util import send_group_forward_msg
from hoshino.util import normalize_str
from .config import Config
from .._model import Setu
from fuzzywuzzy import process

conf = Config.get_instance("setu_search")

if TYPE_CHECKING:
    import re

sv = Service("setu_search")

search_with_author = sv.on_regex(r"^来点(.{1,40})$", only_group=False)

max_once = 3


@search_with_author.handle()
async def send_setu(bot: Bot, event: GroupMessageEvent, state: T_State):
    await bot.send(event, "正在搜索...")
    match: re.Match = state["match"]
    tag_expr: str = match.group(1)
    tag_expr = tag_expr.replace("色图", "")
    tag_expr = tag_expr.replace("涩图", "")
    if not tag_expr:
        return
    tags = tag_expr.split("+")
    if len(tags) > 1:
        keyword = tags[-1]
        tags = tags[:-1]
    else:
        keyword, tags = get_parser().parse(tag_expr)

    sv.logger.info(f"keyword: {keyword} tags: {tags}")
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
        if yande_tags:
            return await search_yande(yande_tags), yande_tags
        else:
            return [], []

    if conf.mode == 0:
        sv.logger.info("trying to translate to yande tag")
        setus, hit_tags = await get_setus_from_yande([keyword] + tags)
        sv.logger.info(f"yande found {len(setus)}")

        if not setus:  # yande not found, try pixiv
            sv.logger.info(
                f"yande not found, try pixiv keyword = {keyword}, tags = {tags}"
            )
            setus, hit_tags = await search_by_tag(keyword, tags)
            sv.logger.info(f"pixiv found {len(setus)} setus")

        if len(setus) > max_once:
            setus = random.sample(setus, max_once)

    elif conf.mode == 1:
        sv.logger.info(f"keyword = {keyword}, tags = {tags}")
        setus, hit_tags = await search_by_tag(keyword, tags)
        sv.logger.info(f"found {len(setus)} setus")

        if not setus:  # pixel not found, try yande
            sv.logger.info(f"trying to translate {keyword} to yande tag")
            setus, hit_tags = await get_setus_from_yande([keyword] + tags)
        if len(setus) > max_once:
            setus = random.sample(setus, max_once)

    elif conf.mode == 2:
        sv.logger.info(f"trying to translate {keyword} to yande tag")
        setus, hit_tags = await get_setus_from_yande([keyword] + tags)

        sv.logger.info(f"keyword = {keyword}, tags = {tags}")
        setus_database, hit_tags_databbase = await search_by_tag(keyword, tags)
        setus.extend(setus_database)
        hit_tags.extend(hit_tags_databbase)
        sv.logger.info(f"found {len(setus)} setus")
        if len(setus) > max_once:
            setus = random.sample(setus, max_once)

    if not setus:
        await bot.send(event, f"没有找到关键字为{keyword}的色图")
        return

    # msgs = [MessageSegment.text(f'关键字: {keyword} 命中tag: {",".join(hit_tags)}')]
    # for setu in setus:
    #     anti_harmony = True if setu.r18 else False
    #     try:
    #         sv.logger.info(f"downloading {setu.url}")
    #         msgs.append(
    #             await R.image_from_url(setu.url, anti_harmony=anti_harmony, timeout=30)
    #         )
    #         sv.logger.info(f"download finished")
    #     except Exception as e:
    #         sv.logger.error(f"{setu.url} url error: {e}")
    # sv.logger.info(f"sending group forward msg...")
    # await send_group_forward_msg(bot, event.group_id, msgs)
    setu = random.choice(setus)
    anti_harmony = True if setu.r18 else False
    pic = await R.image_from_url(setu.url, anti_harmony=anti_harmony, timeout=30)
    await bot.send(event, pic)
