from typing import Dict, Type

from hoshino import Bot, Service
from hoshino.modules.infopush.checkers.bilidynamic import BiliDynamicChecker
from hoshino.modules.infopush.checkers.bililive import BiliLiveChecker
from hoshino.modules.infopush.checkers.bilivideo import BiliVideoChecker
from hoshino.modules.infopush.checkers.fanbox import FanboxChecker
from hoshino.modules.infopush.checkers.pixivuser import PixivUserChecker
from hoshino.modules.infopush.checkers.twitter import TwitterChecker
from hoshino.modules.infopush.checkers.weibo import WeiboChecker
from hoshino.typing import GroupMessageEvent, T_State
from hoshino.util.proxypool import ProxyException
from hoshino.util import aiohttpx
from hoshino.util.handle_msg import handle_msg

from ._exception import NetworkException, ProxyException, TimeoutException
from ._model import BaseInfoChecker, InfoData
from ._config import Config

help_ = """
[/p]: Pixiv投稿
[/wb]: 微博
[/t]: 推特
[/bl]: B站直播
[/bd]: B站动态
[/bv]: B站投稿
[/fan]: fanbox
示例： /p 16731 添加毛玉老师的插画更新提醒
""".strip()

cmds: Dict[str, Type['BaseInfoChecker']] = {
    '/p': PixivUserChecker,
    '/wb': WeiboChecker,
    '/t': TwitterChecker,
    '/bl': BiliLiveChecker,
    '/bd': BiliDynamicChecker,
    '/bv': BiliVideoChecker,
    '/fan': FanboxChecker
}

sv = Service("订阅精简版", help_=help_)

async def add_sub(bot: Bot, event: GroupMessageEvent, state: T_State):
    checker = cmds[state['_prefix']['raw_command']]
    dis = str(event.get_message()).strip()
    url = checker.form_url(dis)
    try:
        data = await checker.get_data(url)
    except (ProxyException, TimeoutException, NetworkException) as e:
        sv.logger.warning(f'订阅{checker.name}获取数据超时')
        data = InfoData() # 使用proxy pool 超时是正常情况
    except Exception as e:
        await bot.send(event, f"error: {e}")
        return

    if data is None:
        await bot.send(event, "获取数据失败, 请检查输入")
    gid = event.group_id
    uid = str(event.user_id)
    try:
        remark = checker.form_remark(data, dis)
    except ValueError as e:
        await bot.send(event, "获取数据失败，请检查输入")
        return

    try:
        checker.add_sub(gid, url, remark=remark, creator_id=uid)
        await bot.send(event, f"成功订阅{remark}")
    except Exception as e:
        sv.logger.error(e)
        await bot.send(event, f"error: {e}")

for cmd, checker in cmds.items():
    sv.on_command(cmd, only_group=True).handle()(add_sub)

fb = sv.on_command('fanbox bind')

@fb.handle()
async def bind(bot: Bot, event: GroupMessageEvent, state: T_State):
    uid = event.user_id
    fan_cookie = str(event.get_message()).strip()
    conf = Config.get_instance('infopush')
    headers = {
        'Origin': 'https://www.fanbox.cc',
        'Cookie': f'FANBOXSESSID={fan_cookie}'
    }
    resp = await aiohttpx.get('https://api.fanbox.cc/creator.listFollowing', headers=headers)
    if resp.status_code != 200:
        await bot.send(event, resp.json)
    follows = resp.json['body']
    for fl in follows:
        cid = fl['creatorId']
        await handle_msg(bot, event, f'/fan {cid}')
    conf.fanbox_cookies[uid] = fan_cookie
    await bot.send(event, '绑定成功')

