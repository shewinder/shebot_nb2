"""
AI Tool: 广播消息
向多个群组发送消息/图片
"""
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from loguru import logger

from ..registry import tool_registry, ok, fail
from hoshino import get_bot_list

if TYPE_CHECKING:
    from hoshino import Event
    from ...session import Session


@tool_registry.register(
    name="broadcast",
    description="""向多个群组广播发送消息或图片。

用于定时任务、群发通知等场景。支持发送文本和图片（通过图片标识符）。

## 使用场景
- 定时推送：每天晚上推送日榜到指定群
- 群发通知：向多个群发送相同消息
- 图片广播：将生成的图片发送到多个群

## 权限检查
- 机器人必须在目标群中
- 任务创建者必须在目标群中（防止误发到无关群）

## 图片发送
通过图片标识符发送已存储的图片：
- 用户图片：<user_image_1>, <user_image_2>...
- AI生成的图片：<ai_image_1>, <ai_image_2>...

## 示例
- 发送文本：broadcast(groups=[123456, 789012], content="晚上好！")
- 发送图片：broadcast(groups=[123456], content="今日Pixiv日榜：", image_identifiers=["<ai_image_1>"])
- 混合发送：broadcast(groups=[111, 222], content="看看这张图：", image_identifiers=["<ai_image_1>", "<ai_image_2>"])

注意：如果机器人在某个群中不可达，会跳过该群并记录警告，其他群正常发送。""",
    parameters={
        "type": "object",
        "properties": {
            "groups": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "目标群号列表，如 [123456, 789012]"
            },
            "content": {
                "type": "string",
                "description": "要发送的文本内容。空字符串表示只发送图片"
            },
            "image_identifiers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "图片标识符列表（可选），如 [\"<ai_image_1>\", \"<user_image_1>\"]"
            }
        },
        "required": ["groups", "content"]
    }
)
async def broadcast(
    groups: List[int],
    content: str,
    image_identifiers: Optional[List[str]] = None,
    session: Optional["Session"] = None,
    event: Optional["Event"] = None,
) -> Dict[str, Any]:
    """
    广播消息到多个群
    
    Args:
        groups: 目标群号列表
        content: 文本内容
        image_identifiers: 图片标识符列表（可选）
        session: 会话对象（自动注入）
        event: 事件对象（自动注入）
    
    Returns:
        发送结果
    """
    if not groups:
        return fail("请提供目标群号列表", error="Empty groups")
    
    # 获取发送者信息
    sender_user_id = None
    if event:
        sender_user_id = getattr(event, 'user_id', None)
    elif session:
        sender_user_id = session.user_id
    
    # 获取 Bot 实例
    bots = get_bot_list()
    if not bots:
        return fail("没有可用的 Bot", error="No bot available")
    bot = bots[0]
    
    # 权限校验：检查机器人在哪些目标群中
    valid_groups = []
    invalid_groups = []
    
    for group_id in groups:
        try:
            # 尝试获取群信息来验证机器人在群中
            info = await bot.get_group_info(group_id=group_id)
            if info:
                valid_groups.append(group_id)
            else:
                invalid_groups.append((group_id, "无法获取群信息"))
        except Exception as e:
            invalid_groups.append((group_id, f"不在该群或无法访问: {str(e)[:50]}"))
    
    if not valid_groups:
        return fail(
            f"机器人不在任何指定的群中。\n无效群: {', '.join(str(g) for g, _ in invalid_groups)}",
            error="Bot not in groups"
        )
    
    # 构建完整消息（content 中可能包含图片标识符）
    # 将额外的图片标识符追加到内容中
    if image_identifiers:
        identifiers_str = " ".join(image_identifiers)
        content = f"{content} {identifiers_str}" if content else identifiers_str
    
    messages = await session.build_message(content) if session else []
    
    # 发送消息到各群
    success_groups = []
    failed_groups = []
    
    for group_id in valid_groups:
        try:
            # 发送所有消息
            for msg in messages:
                await bot.send_group_msg(group_id=group_id, message=msg)
            
            success_groups.append(group_id)
            logger.info(f"广播成功发送到群 {group_id}")
            
        except Exception as e:
            failed_groups.append((group_id, str(e)[:100]))
            logger.error(f"广播到群 {group_id} 失败: {e}")
    
    # 构建返回结果
    result_lines = []
    
    if success_groups:
        result_lines.append(f"✅ 成功发送到 {len(success_groups)} 个群: {', '.join(map(str, success_groups))}")
    
    if invalid_groups:
        result_lines.append(f"⚠️ {len(invalid_groups)} 个群无效（机器人不在群中）:")
        for gid, reason in invalid_groups:
            result_lines.append(f"  - 群{gid}: {reason}")
    
    if failed_groups:
        result_lines.append(f"❌ {len(failed_groups)} 个群发送失败:")
        for gid, reason in failed_groups:
            result_lines.append(f"  - 群{gid}: {reason}")
    
    # 统计图片数量（从所有消息中统计图片段）
    image_count = 0
    for msg in messages:
        for seg in msg:
            if seg.type == "image":
                image_count += 1
    
    if image_count > 0:
        result_lines.append(f"\n📷 已发送 {image_count} 张图片")
    
    return ok(
        "\n".join(result_lines),
        metadata={
            "success_count": len(success_groups),
            "failed_count": len(failed_groups) + len(invalid_groups),
            "success_groups": success_groups,
            "failed_groups": [g for g, _ in failed_groups],
            "invalid_groups": [g for g, _ in invalid_groups],
            "image_count": image_count
        }
    )
