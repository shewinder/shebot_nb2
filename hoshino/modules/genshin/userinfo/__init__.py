from nonebot.typing import T_State
from hoshino import Service, Bot
from nonebot.adapters.cqhttp.event import GroupMessageEvent

from .data_source import *

sv = Service('原神信息')
info_query = sv.on_command('原神信息')

@info_query.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    uid = str(event.get_message())
    uid = uid.lstrip('0')
    if uid:
        state['uid'] = uid

@info_query.got('uid', prompt='请输入原神信息uid（仅支持国服） 如：原神信息100692770')
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    uid = state['uid']
    if (len(uid) == 9):
        if (uid[0] == "1"):
            sv.logger.info('原神查询uid中')
            await bot.send(event, '原神查询uid中')


            mes = await JsonAnalysis(await GetInfo(uid, "cn_gf01"), uid, "cn_gf01")
            await bot.send(event , mes, at_sender=True)
            #await bot.send_group_forward_msg(group_id=ev['group_id'], messages=tas_list)
        elif (uid[0] == "5"):
            sv.logger.info('原神查询uid中')
            mes = JsonAnalysis(GetInfo(uid, "cn_qd01"), uid, "cn_qd01")
            await bot.send(event , mes, at_sender=True)
            #await bot.send_group_forward_msg(group_id=ev['group_id'], messages=tes_list)
        else:
            sv.logger.info('原神uid不对')
            await bot.send(event, 'UID输入有误！\n请检查UID是否为国服UID！', at_sender=True)
    else:
        sv.logger.info('invalid uid')
        await bot.send(event, 'UID长度有误！\n请检查输入的UID是否为9位数！', at_sender=True)
