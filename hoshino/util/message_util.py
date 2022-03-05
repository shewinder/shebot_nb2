from typing import List
from hoshino import MessageSegment, Bot, Message
from hoshino.typing import GroupMessageEvent
from hoshino import hsn_config, Bot, get_bot_list


async def send_group_forward_msg(bot: Bot, group_id: int, msgs: List[Message]) -> int:
    ms = []
    for msg in msgs:
        ms.append(
            MessageSegment(
                "node",
                {
                    "user_id": bot.self_id,
                    "name": list(hsn_config.nickname)[0],
                    "content": msg
                }
            )
        )
    id = await bot.send_group_forward_msg(group_id=group_id, messages=ms)
    return id

async def send_group_msg(group_id: int, msg: Message) ->int:
    bot = get_bot_list()[0]
    await bot.send_group_msg(group_id=group_id, message=msg)