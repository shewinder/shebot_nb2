import random
from typing import TYPE_CHECKING
from hoshino import Service, GroupMessageEvent, Bot, T_State
from hoshino.sres import Res as R
from .._tag_parser import parser
from .search import search_by_tag
from hoshino.util.message_util import send_group_forward_msg
from pathlib import Path

if TYPE_CHECKING:
    import re

sv = Service("setu_search")

search_with_author = sv.on_regex(r"^来点(.{0,20})$", only_group=False)


@search_with_author.handle()
async def send_setu(bot: Bot, event: GroupMessageEvent, state: T_State):
    await bot.send(event, "正在搜索...")
    match: re.Match = state["match"]
    tag_expr: str = match.group(1)
    tag_expr = tag_expr.replace("色图", "")
    if not tag_expr:
        return
    keyword, tags = parser.parse(
        tag_expr
    )
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
        msgs.append(
            await R.image_from_url(
                setu.url,
                anti_harmony=anti_harmony,
            )
        )
    sv.logger.info(f'sending group forward msg...')
    await send_group_forward_msg(bot, event.group_id, msgs)
