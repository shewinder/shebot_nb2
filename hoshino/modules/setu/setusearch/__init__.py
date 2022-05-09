import random
from typing import TYPE_CHECKING, List, Tuple
from hoshino import Service, GroupMessageEvent, Bot, T_State
from hoshino.sres import Res as R
from ..sync_tag import get_parser, get_translate
from .search import search_by_tag, search_yande
from hoshino.util.message_util import send_group_forward_msg
from .config import Config
from .._model import Setu
from fuzzywuzzy import process

conf = Config.get_instance('setu_search')

if TYPE_CHECKING:
    import re

sv = Service("setu_search")

search_with_author = sv.on_regex(r"^来点(.{0,40})$", only_group=False)


@search_with_author.handle()
async def send_setu(bot: Bot, event: GroupMessageEvent, state: T_State):
    await bot.send(event, "正在搜索...")
    match: re.Match = state["match"]
    tag_expr: str = match.group(1)
    tag_expr = tag_expr.replace("色图", "")
    if not tag_expr:
        return
    keyword, tags = get_parser().parse(
        tag_expr
    )

    if tags: # 多个tag搜索用pixiv（本地图库）
        sv.logger.info(f'keyword = {keyword}, tags = {tags}')
        setus, hit_tags = await search_by_tag(keyword, tags)
        sv.logger.info(f'found {len(setus)} setus')
        if len(setus) > 5:
            setus = random.sample(setus, 5)
        if not setus:
            await bot.send(event, f"没有找到关键字为{keyword}包含tag{tags}的色图")
            return

        msgs = [f'关键字: {keyword} 命中tag: {",".join(hit_tags)}']
        for setu in setus:
            anti_harmony = True if setu.r18 else False
            try:
                msgs.append(
                    await R.image_from_url(
                        setu.url,
                        anti_harmony=anti_harmony,
                    )
                )
            except Exception as e:
                sv.logger.error(e)
        sv.logger.info(f'sending group forward msg...')
        await send_group_forward_msg(bot, event.group_id, msgs)
        return

    # 根据mode 分情况处理单个tag搜索
    setus: List[Setu] = []
    if conf.mode == 0:
        sv.logger.info(f'trying to translate {keyword} to yande tag')
        trans = get_translate()
        res = process.extractOne(keyword, trans.keys(), score_cutoff=95)
        if res:
            t, score = tuple(res)
            sv.logger.info(f'{keyword} match yande tag {t}, score {score}, tranlated {trans[t]}')
            setus = await search_yande([trans[t]])
            sv.logger.info(f'yande found {len(setus)}')

        if not setus: # yande not found, try pixiv
            sv.logger.info(f'yande not found, try pixiv keyword = {keyword}, tags = {tags}')
            setus, hit_tags = await search_by_tag(keyword, tags)
            sv.logger.info(f'pixiv found {len(setus)} setus')
        if len(setus) > 5:
            setus = random.sample(setus, 5)

    elif conf.mode == 1:
        sv.logger.info(f'keyword = {keyword}, tags = {tags}')
        setus, hit_tags = await search_by_tag(keyword, tags)
        sv.logger.info(f'found {len(setus)} setus')

        if not setus: # pixel not found, try yande
            sv.logger.info(f'trying to translate {keyword} to yande tag')
            trans = get_translate()
            res = process.extractOne(keyword, trans.keys(), score_cutoff=95)
            if res:
                t, score = tuple(res)
                sv.logger.info(f'{keyword} match yande tag {t}, score {score}, tranlated {trans[t]}')
                setus = await search_yande([trans[t]])
                sv.logger.info(f'yande found {len(setus)}')
        if len(setus) > 5:
            setus = random.sample(setus, 5)
    
    elif conf.mode == 2:
        sv.logger.info(f'trying to translate {keyword} to yande tag')
        trans = get_translate()
        res = process.extractOne(keyword, trans.keys(), score_cutoff=95)
        if res:
            t, score = tuple(res)
            sv.logger.info(f'{keyword} match yande tag {t}, score {score}, tranlated {trans[t]}')
            setus = await search_yande([trans[t]])

        sv.logger.info(f'keyword = {keyword}, tags = {tags}')
        setus_pix, hit_tags = await search_by_tag(keyword, tags)
        setus.extend(setus_pix)
        sv.logger.info(f'found {len(setus)} setus')
        if len(setus) > 5:
            setus = random.sample(setus, 5)



    if not setus:
        await bot.send(event, f"没有找到关键字为{keyword}的色图")
        return

    msgs = [f'关键字: {keyword}']
    for setu in setus:
        anti_harmony = True if setu.r18 else False
        try:
            sv.logger.info(f'downloading {setu.url}')
            msgs.append(
                await R.image_from_url(
                    setu.url,
                    anti_harmony=anti_harmony,
                    timeout=60
                )
            )
            sv.logger.info(f'download finished')
        except Exception as e:
            sv.logger.error(f'{setu.url} url error: {e}')
    sv.logger.info(f'sending group forward msg...')
    await send_group_forward_msg(bot, event.group_id, msgs)
