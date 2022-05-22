from typing import List, Union
from hoshino import MessageSegment, Bot, Message
from hoshino.typing import GroupMessageEvent
from hoshino import hsn_config, Bot, get_bot_list


async def send_group_forward_msg(bot: Bot, group_id: int, msgs: List[Union[Message, List]]) -> int:
    def _to_node(msg: Message):
        return MessageSegment(
            "node",
            {
                "user_id": bot.self_id,
                "name": list(hsn_config.nickname)[0],
                "content": msg
            }
        )
    def _dfs(msgs: List[Union[Message, MessageSegment, List]]):
        _ms = []
        for msg in msgs:
            if isinstance(msg, MessageSegment) and msg.type != "node":
                _ms.append(_to_node(Message(msg)))
                continue
            if isinstance(msg, Message):
                _ms.append(_to_node(msg))
            if isinstance(msg, list):
                _ms.append(_to_node(_dfs(msg)))
        return _ms      
         
    id = await bot.send_group_forward_msg(group_id=group_id, messages=_dfs(msgs))
    return id

async def send_group_msg(group_id: int, msg: Message) ->int:
    bot = get_bot_list()[0]
    await bot.send_group_msg(group_id=group_id, message=msg)