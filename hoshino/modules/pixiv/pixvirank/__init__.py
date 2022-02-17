import asyncio
import datetime
from pathlib import Path

from hoshino import Bot, Event, Service, get_bot_list, scheduled_job, userdata_dir
from hoshino.sres import Res as R
from hoshino.util.sutil import get_service_groups, load_config, save_config
from nonebot.adapters.cqhttp.message import Message, MessageSegment

from .data_source import filter_rank, get_rank, get_tags

help_ = """
启用后会每天固定推送Pixiv日榜
(该功能还在完善中)
""".strip()

sv = Service('Pixiv日榜', enable_on_default=False, help_=help_)

plugin_dir = userdata_dir.joinpath('pixiv')
if not plugin_dir.exists():
    plugin_dir.mkdir()
p = plugin_dir.joinpath('tag.json')
if not p.exists():
    p.touch()
_tag_scores = load_config(p)

@scheduled_job('cron', hour=18, minute=30, id='pixiv日榜')
async def pixiv_rank():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    date = f'{yesterday}'
    sv.logger.info("正在下载日榜图片")
    pics = await get_rank(date)
    sv.logger.info("日榜图片下载完成")
    pics = filter_rank(pics, _tag_scores)
    bot: Bot = get_bot_list()[0]
    gids = await get_service_groups(sv_name=sv.name)
    count = 0
    msg = MessageSegment.text('今日Pixiv日榜:\n')
    for pic in pics:
        msg += MessageSegment.text(f'{pic.pid}: {pic.page_count}') + MessageSegment.image(pic.url)

    for gid in gids:
        await asyncio.sleep(0.5)
        try:
            await bot.send_group_msg(message=msg, group_id=gid)
            count += 1
            sv.logger.info(f"群{gid} 投递成功！")
        except Exception as e:
            sv.logger.exception(e)
            sv.logger.error(type(e))

add_tag = sv.on_command('add pid', only_to_me=False)
@add_tag.handle()
async def _(bot: Bot, event: Event):
    global _tag_scores
    try:
        pid, score = str(event.message).split(' ')
    except:
        pid = str(event.message).strip()
        score = 1
    tags = await get_tags(pid)
    for tag in tags:
        if tag in _tag_scores:
            _tag_scores[tag] += int(score)
            #pass
        else:
            _tag_scores[tag] = int(score)
    save_config(_tag_scores, p)
    await bot.send(event, f'更新tag {tags}')

add_pid = sv.on_command('add tag', only_to_me=False)
@add_pid.handle()
async def _(bot: Bot, event: Event):
    global _tag_scores
    try:
        tag, score = str(event.message).split(' ')
    except:
        tag = str(event.message)
        score = 1
    if tag in _tag_scores:
        _tag_scores[tag] += int(score)
    else:
        _tag_scores[tag] = int(score)
    save_config(_tag_scores, p)
    await bot.send(event, f'更新tag {tag}')