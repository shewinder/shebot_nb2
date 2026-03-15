import json
from typing import List, Union, Optional, Dict, Any
from hoshino import MessageSegment, Bot, Message
from hoshino.event import GroupMessageEvent
from hoshino import hsn_config, Bot, get_bot_list
from pydantic import BaseModel
from nonebot.adapters.onebot.v11.event import Reply
from nonebot.adapters.onebot.v11 import Event


async def get_forward_msg_images(bot: Bot, forward_id: str) -> List[str]:
    """
    获取转发消息中的所有图片 URL
    
    Args:
        bot: Bot 实例
        forward_id: 转发消息的 ID
        
    Returns:
        图片 URL 列表
    """
    imglist: List[str] = []
    
    try:
        # 调用 OneBot API 获取转发消息内容
        forward_data = await bot.call_api("get_forward_msg", id=forward_id)
        
        if forward_data and 'messages' in forward_data:
            # 遍历转发消息中的每条消息
            for msg_item in forward_data['messages']:
                if 'content' in msg_item:
                    msg_content = msg_item['content']
                    # message 可能是列表或 Message 对象
                    if isinstance(msg_content, list):
                        for seg in msg_content:
                            if isinstance(seg, dict) and seg.get('type') == 'image':
                                seg_data = seg.get('data', {})
                                if 'url' in seg_data:
                                    imglist.append(seg_data['url'])
                    elif hasattr(msg_content, '__iter__'):
                        # Message 对象
                        for seg in msg_content:
                            if hasattr(seg, 'type') and seg.type == 'image' and hasattr(seg, 'data') and 'url' in seg.data:
                                imglist.append(seg.data['url'])
    except Exception as e:
        # 获取转发消息失败时，记录错误但返回空列表
        import logging
        logging.getLogger(__name__).warning(f"获取转发消息失败: {e}")
    
    return imglist


async def extract_images_from_reply(event: Event, bot: Optional[Bot] = None) -> List[str]:
    """
    从引用消息中提取图片 URL
    
    支持普通消息和转发消息（当提供 bot 参数时）
    
    Args:
        event: 消息事件
        bot: Bot 实例，用于获取转发消息内容。如果为 None，则无法处理转发消息
        
    Returns:
        图片 URL 列表
    """
    if not hasattr(event, "reply"):
        return []
    
    if not event.reply:
        return []
    
    reply: Reply = event.reply
    imglist: List[str] = []
    
    # 从普通消息中提取图片
    for s in reply.message:
        if s.type == 'image' and 'url' in s.data:
            imglist.append(s.data['url'])
    
    # 检查是否是转发消息
    forward_seg = None
    for s in reply.message:
        if s.type == 'forward':
            forward_seg = s
            break
    
    # 如果是转发消息且提供了 bot，获取转发消息内容
    if forward_seg and bot and 'id' in forward_seg.data:
        forward_id = forward_seg.data['id']
        forward_images = await get_forward_msg_images(bot, forward_id)
        imglist.extend(forward_images)
    
    return imglist


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