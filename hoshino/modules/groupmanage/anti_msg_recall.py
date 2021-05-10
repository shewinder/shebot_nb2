from nonebot.adapters.cqhttp.message import Message
from nonebot.adapters.cqhttp import GroupRecallNoticeEvent

from hoshino import Service, Bot

sv = Service('反撤回', enable_on_default=False)

anti = sv.on_notice('group_recall')
@anti.handle()
async def antiwithdraw(bot: "Bot", event: "GroupRecallNoticeEvent"):
    gid = event.group_id
    mid = event.message_id
    uid = event.user_id
    oid = event.operator_id
    msg = await bot.get_msg(message_id=mid)
    user = await bot.get_group_member_info(group_id=gid, user_id=uid)
    if oid == uid and uid != event.self_id:
        await anti.send(
            f'{user["card"]}({uid})撤回的消息是:\n' + Message(msg["message"])
        )
