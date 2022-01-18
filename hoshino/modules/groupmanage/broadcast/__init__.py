import asyncio
from loguru import logger

from hoshino import Service, sucmd, Bot, Event
from hoshino import permission
from hoshino.permission import SUPERUSER
from hoshino.rule import to_me
from hoshino.util.sutil import get_service_groups

sv = Service('broadcast', manage_perm=SUPERUSER)
bc = sv.on_command('bc', aliases={'广播', 'broadcast'}, permission = SUPERUSER,  only_group=False)

@bc.handle()
async def bc(bot: Bot, event: Event):
    msg = event.get_message()
    gids = await get_service_groups('broadcast')
    count = 0
    for gid in gids:
        await asyncio.sleep(0.5)
        try:
            await bot.send_group_msg(message=msg, group_id=gid)
            count += 1
            logger.info(f"群{gid} 投递成功！")
        except Exception as e:
            logger.exception(e)
            logger.error(type(e))
            await bot.send(event, f"群{gid} 投递失败：\n {type(e)} {e}")
    await bot.send(event, f'广播完成,投递成功{count}个群')

