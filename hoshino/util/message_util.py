import json
from typing import List, Union
from hoshino import MessageSegment, Bot, Message
from hoshino.typing import GroupMessageEvent
from hoshino import hsn_config, Bot, get_bot_list
from pydantic import BaseModel


async def send_group_forward_msg(bot: Bot, group_id: int, msgs: List[Union[Message, List]]) -> int:
    def _to_node(msg: Message):
        return MessageSegment(
            "node",
            {
                "uin": bot.self_id,
                "nickname": list(hsn_config.nickname)[0],
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


async def send_group_mutiple_msgs(bot: Bot, group_id: int, msgs: List[MessageSegment], mode: str="forward"):
    """
    mode: forward 合并转发 sequence 顺序单条发送
    """
    if mode == "forward":
        await send_group_forward_msg(bot, group_id, msgs)
    elif mode == "sequence":
        await bot.send_group_msg(group_id=group_id, message=msgs)






class RenderData(BaseModel):
    label: str # 按钮上的文字
    visited_label: str # 点击后按钮的上文字


class Permission(BaseModel):
    type: int = 2 # 0 指定用户可操作，1 仅管理者可操作，2 所有人可操作
    specify_user_ids: List[str] = [] # 有权限的用户 id 的列表


class Action(BaseModel):
    type: int = 2 # 设置 0 跳转按钮：http 或 小程序 客户端识别 scheme，设置 1 回调按钮：回调后台接口, data 传给后台，设置 2 指令按钮：自动在输入框插入 @bot data
    enter: bool = False
    permission: Permission = Permission()
    unsupport_tips: str = ""
    data: str


class Button(BaseModel):
    id: str
    render_data: RenderData
    action: Action


class Row(BaseModel):
    buttons: List[Button]


class Keyboard(BaseModel):
    rows: List[Row]


async def send_keyboard(bot: Bot, group_id: int, markdown_str: str, keyboard: Keyboard):
    def _to_node(msg: Message):
        return MessageSegment(
            "node",
            {
                "uin": bot.self_id,
                "name": list(hsn_config.nickname)[0],
                "content": msg
            }
        )
    fake_gid = 907959319
    markdown = MessageSegment("markdown", {"content": json.dumps({"content": markdown_str})})
    keyboard = MessageSegment("keyboard", {"content": keyboard.dict()})
    markdown_with_keyboard = markdown + keyboard
    resid = await bot.send_group_forward_msg(group_id=fake_gid, messages=[_to_node(markdown_with_keyboard)])
    longmsg = MessageSegment("longmsg", {"id": str(resid["forward_id"])})
    await bot.send_group_msg(group_id=group_id, message=longmsg)