import asyncio
from loguru import logger

from hoshino import Service, sucmd, Bot, Event
from hoshino import permission
from hoshino.permission import SUPERUSER
from hoshino.rule import to_me

async def get_send_groups(groups=None, sv_name='broadcast'):
    #bot = nonebot.get_bot()
    #当groups指定时，在groups中广播；当groups未指定，但sv_name指定，将在开启该服务的群广播
    svs = Service.get_loaded_services()
    if not groups and sv_name not in svs:
        raise ValueError(f'不存在服务 {sv_name}')
    if sv_name:
        enable_groups = await svs[sv_name].get_enable_groups()
        send_groups = enable_groups.keys() if not groups else groups
    else:
        send_groups = groups
    return send_groups
    

sv = Service('broadcast', manage_perm=SUPERUSER)
bc = sv.on_command('bc', aliases={'广播', 'broadcast'}, permission = SUPERUSER,  only_group=False)

@bc.handle()
async def bc(bot: Bot, event: Event):
    msg = event.get_message()
    gids = await get_send_groups()
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

