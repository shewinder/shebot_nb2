from hoshino import Service, Bot, GroupMessageEvent
from ._user import User

reg = Service('register', visible=False)

@reg.on_command('register', aliases=('注册', '登录'), only_to_me=True)
async def _(bot: Bot, event: GroupMessageEvent):
    uid = str(event.user_id)
    gid = str(event.group_id)
    user: User = User.get_or_none(User.uid == uid, User.group_id == gid)
    if user:
        await bot.send(event, f'url xxxxx')
        return
    name = event.sender.nickname
    avatar = 'avatar url'
    user = User.create(uid=uid, group_id=gid, name=name, avatar=avatar, password=uid)
    await bot.send(event, f'默认密码为QQ号，请及时修改')
    await bot.send(event, f'url xxxxx')
    

    
    