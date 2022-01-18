from hoshino.service import Service
from nonebot import on_command

from hoshino.typing import Bot, GroupMessageEvent, T_State

help = on_command('help', aliases={'帮助', '机器人帮助', '使用手册'})

#@help.handle()
#async def _(bot, event):
#    await help.send('http://bot.shewinder.win')

tip = """
请附带服务名称 例如"帮助 色图"
查看所有服务请艾特我并发送 lssv
""".strip()

@help.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    sv_name = str(event.get_message()).strip()
    if not sv_name:
        await help.finish(tip)
    svs = Service.get_loaded_services()
    sv = svs.get(sv_name)
    if not sv:
        await help.finish('该服务不存在，艾特机器人并发送 lssv查看所有支持的服务')
    help_ = sv.help
    if not help_:
        await help.finish('该服务帮助正在完善中~')
    await help.send(help_)
