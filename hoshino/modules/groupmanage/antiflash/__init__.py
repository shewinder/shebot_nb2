from hoshino import Bot, Service, GroupMessageEvent
from hoshino.log import logger

sv = Service("反闪照", enable_on_default=False)

flash = sv.on_message()


@flash.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    msg = event.get_message()[0]
    if msg.type == "image":
        if "type" not in msg.data:
            return
        if msg.data["type"] == "flash":
            logger.info(f"检测到群{event.group_id}{event.sender.nickname}发送闪照")
            del msg.data["type"]
            await bot.send(event, f"{event.sender.nickname}发送了闪照" + msg)
