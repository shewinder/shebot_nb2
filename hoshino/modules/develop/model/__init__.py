from hoshino import Bot, Event, Service

sv = Service('name')

matcher = sv.on_command('model', only_to_me=True, only_group=False)

@matcher.handle()
async def _(bot: Bot, event: Event):
    pass