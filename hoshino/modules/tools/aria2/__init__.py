import asyncio
import re
import urllib.parse

import nonebot
from aioaria2 import Aria2WebsocketTrigger
from nonebot.adapters.cqhttp.message import unescape, Message

from hoshino import Service, permission, util
from nonebot.adapters.cqhttp.event import GroupMessageEvent, Optional
from .config import aria2config
from .utils import trans_speed, load_mission, write_mission, del_mission

url_valid = re.compile(
    r'^(?:http|ftp)s?://'  # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
    r'localhost|'  # localhost...
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)$', re.IGNORECASE)

sv = Service('Aria2Download', enable_on_default=False, manage_perm=permission.SUPERUSER)
trigger: Optional[Aria2WebsocketTrigger] = None
begin_download = sv.on_command('远程下载', only_group=True)
global_status = sv.on_command('查看全局统计', only_group=False, permission=permission.SUPERUSER, aliases={"查看全局状态", "查询全局状态"})
query_status = sv.on_command('查询下载状态', aliases={"查询任务状态", "查看任务状态", "查看下载状态"})

driver = nonebot.get_driver()
@driver.on_startup
async def _():
    global trigger
    try:
        trigger = await Aria2WebsocketTrigger.new(aria2config.url, token=aria2config.token)
    except:
        sv.logger.error('aria2 trigger-client failed to create')
    trigger.onDownloadStart(callback_start)
    trigger.onDownloadError(callback_error)
    trigger.onDownloadComplete(callback_finish)
    sv.logger.info('aria2 trigger-client created')


async def callback_start(trigger: Aria2WebsocketTrigger, data: dict):
    await asyncio.sleep(1)  # 不sleep的话gid都没来得及有
    bot = util.get_bot_list()[0]
    gid = data['params'][0]['gid']
    user_id, group_id, _, _ = await load_mission(gid)
    if group_id:
        await bot.send_group_msg(group_id=group_id, message=Message(f'[CQ:at,qq={user_id}]\n下载开始{gid}'))
    else:
        await bot.send_private_msg(user_id=915149147, message=f'下载开始{gid}')


async def callback_finish(trigger: Aria2WebsocketTrigger, data: dict):
    await asyncio.sleep(1)
    bot = util.get_bot_list()[0]
    gid = data['params'][0]['gid']
    user_id, group_id, _, typeid = await load_mission(gid)
    subdic = await trigger.tellStatus(gid, ['followedBy'])
    subgids = subdic.get('followedBy', None)
    if subgids:
        for subgid in subgids:
            await write_mission(mid=subgid, uid=user_id, gid=group_id, typeid='btsub')
        await bot.send_group_msg(group_id=group_id, message=Message(f'[CQ:at,qq={user_id}]\n{gid}种子下载完成，开始下载种子内文件'))
    else:
        file_data = await trigger.tellStatus(gid)
        path = file_data["files"][0]["path"][len(aria2config.local_path):]
        path = urllib.parse.quote(path)
        await bot.send_group_msg(group_id=group_id, message=Message(
            f'[CQ:at,qq={str(user_id)}]\n任务{gid}已完成！\n地址:{aria2config.base_url}{path}'))


async def callback_error(trigger: Aria2WebsocketTrigger, data: dict):
    await asyncio.sleep(1)
    bot = util.get_bot_list()[0]
    gid = data['params'][0]['gid']
    user_id, group_id, _, _ = await load_mission(gid)
    if group_id:
        await bot.send_group_msg(group_id=group_id, message=f'下载{gid}出错')
    else:
        await bot.send_private_msg(user_id=915149147, message=f'下载{gid}出错')


@nonebot.export()
async def aria2_download(uri: str, user_id: Optional[int] = None, group_id: Optional[int] = None,
                         bot_id: Optional[int] = None, name: Optional[str] = None):
    if url_valid.match(uri) is None:
        type_id = 'BT'
    else:
        type_id = 'HTTP'
    mid: str = await trigger.addUri([uri], options={"out": name.replace(' ', '')}) if name else await trigger.addUri([uri])
    if mid:
        await write_mission(mid, user_id, group_id, bot_id, type_id)
        return '任务添加成功\n任务ID：' + mid
    else:
        return '发生意外'


@begin_download.handle()
async def _(bot, event: GroupMessageEvent):
    msg = str(event.message).split()
    if len(msg) > 2:
        await begin_download.finish("输入了多余的参数")
    url = msg[0]
    url = unescape(url)
    if len(msg) == 2:
        name = msg[1]
    else:
        name = None
    ret = await aria2_download(url, event.user_id, event.group_id, event.self_id, name)
    await begin_download.finish(Message(ret))
    return


@query_status.handle()
async def query_status(bot, event):
    msg = str(event.message)
    result = await trigger.tellStatus(gid=msg)
    if result["status"] == "active":
        downloadSpeed = result["downloadSpeed"]
        downloadSpeed = trans_speed(downloadSpeed)
        completedLength = result["completedLength"]
        totalLength = result["totalLength"]
        bfb = (int(completedLength) / int(totalLength)) * 100
        bfb = str(bfb)[0:5]
        msg = f"任务{msg}进行中\n当前速度:{downloadSpeed}\n任务进度:{bfb}%"
        await bot.send(event, msg)
        return
    elif result["status"] == "paused":
        completedLength = result["completedLength"]
        totalLength = result["totalLength"]
        bfb = (int(completedLength) / int(totalLength)) * 100
        bfb = str(bfb)[0:5]
        await bot.send(event, f"任务{msg}已暂停\n当前进度:{bfb}%")
        return
    elif result["status"] == "error":
        errorcode = result["errorCode"]
        errormsg = result["errorMessage"]
        await del_mission(msg)
        msg = f"任务{msg}出错！\n错误代码:{errorcode}\n错误信息:{errormsg}"
        await bot.send(event, msg)
        return
    elif result["status"] == "complete":
        await del_mission(msg)
        path = result["files"][0]["path"][len(aria2config.local_path):]
        path = urllib.parse.quote(path)
        msg = f"任务{msg}下载完成\n地址:{aria2config.base_url}{path}"
        await bot.send(event, msg)
        return
    else:
        status = result["status"]
        msg = f"Unknown Status:{status}"
        await bot.send(event, msg)
        return


@global_status.handle()
async def get_global_status(bot, event):
    result = await trigger.getGlobalStat()
    downloadSpeed = result["downloadSpeed"]
    downloadSpeed = trans_speed(downloadSpeed)
    numActive = result["numActive"]
    numStopped = result["numStopped"]
    numStoppedTotal = result["numStoppedTotal"]
    numWaiting = result["numWaiting"]
    uploadSpeed = result["uploadSpeed"]
    uploadSpeed = trans_speed(uploadSpeed)
    msg = f"Aria2全局统计:\n当前下载速度:{downloadSpeed}\n当前上传速度:{uploadSpeed}\n当前活动任务:{numActive}\n当前暂停任务:{numStopped}\n累计暂停任务:{numStoppedTotal}\n当前等待任务:{numWaiting}"
    await bot.send(event, msg)
