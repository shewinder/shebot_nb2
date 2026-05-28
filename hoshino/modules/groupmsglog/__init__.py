"""群聊消息记录模块

功能介绍：
  自动记录所有（或指定）群聊消息到 SQLite 数据库。
  提供查询接口，供群消息总结、群友用户画像等下游功能使用。

命令（需要权限）：
  群消息统计 [天数]  查看本群最近 N 天的消息统计，默认 7 天
"""

from loguru import logger

from hoshino import Bot, Event, Service
from hoshino.permission import ADMIN
from hoshino.typing import T_State

from ._data import (
    GroupMessage,
    db,
    cleanup_old_messages,
    get_group_stats,
)
from .config import Config

sv = Service('groupmsglog', enable_on_default=True, visible=False)
conf = Config.get_instance('groupmsglog')


def _get_message_type(message) -> str:
    types = []
    for seg in message:
        if seg.type not in types:
            types.append(seg.type)
    return ','.join(types) if types else 'unknown'


@sv.on_message(priority=1, block=False, only_group=True).handle()
async def record_group_message(bot: Bot, event: Event, state: T_State):
    group_id = event.group_id

    # 是否记录机器人自己的消息
    if not conf.record_self_message and event.user_id == event.self_id:
        return

    message_type = _get_message_type(event.message)

    # 类型过滤
    if conf.filter_message_types and message_type not in conf.filter_message_types:
        return

    # 提取内容
    content = event.message.extract_plain_text()
    raw_message = str(event.message)

    # 获取发送者信息
    sender = event.sender
    nickname = getattr(sender, 'nickname', '') or ''
    card = getattr(sender, 'card', '') or ''

    try:
        db.connect()
        GroupMessage.create(
            message_id=event.message_id,
            group_id=group_id,
            user_id=event.user_id,
            nickname=nickname,
            card=card,
            content=content,
            raw_message=raw_message,
            message_type=message_type,
            seq=getattr(event, 'message_seq', None),
            time=event.time,
        )
    except Exception:
        # 消息 ID 重复或写入失败不影响 bot 正常运行
        pass
    finally:
        if not db.is_closed():
            db.close()


# 定期清理旧消息（每天触发一次）
_cleanup_day_mark = [0]


@sv.on_message(priority=1, block=False, only_group=True).handle()
async def periodic_cleanup(bot: Bot, event: Event, state: T_State):
    """借助每次消息进行一次清理检查（同一天只触发一次）"""
    import time
    from datetime import datetime

    if conf.retention_days <= 0 and conf.max_messages_per_group <= 0:
        return

    today = datetime.now().day
    if _cleanup_day_mark[0] == today:
        return
    _cleanup_day_mark[0] = today

    try:
        if conf.retention_days > 0:
            deleted = cleanup_old_messages(conf.retention_days)
            if deleted > 0:
                logger.info(f'[groupmsglog] 清理过期消息 {deleted} 条')
    except Exception:
        pass


# 查询命令
stat_cmd = sv.on_command('群消息统计', only_group=True, permission=ADMIN)


@stat_cmd.handle()
async def handle_group_stats(bot: Bot, event: Event, state: T_State):
    args = str(event.message).strip().split()
    days = 7
    if len(args) > 1:
        try:
            days = int(args[1])
        except ValueError:
            pass

    try:
        stats = get_group_stats(event.group_id, days=days)
    except Exception as e:
        logger.error(f'[groupmsglog] 查询统计失败: {e}')
        await stat_cmd.finish("查询统计失败，请稍后重试")

    msg = (
        f"本群最近 {days} 天消息统计：\n"
        f"总消息数：{stats['total_messages']}\n"
    )
    if stats['top_users']:
        msg += "\n发言排行：\n"
        for uid, count in stats['top_users'][:10]:
            msg += f"  {uid}: {count} 条\n"
    await stat_cmd.finish(msg)
