from nonebot import on_command

help = on_command('help', aliases={'帮助', '机器人帮助', '使用手册'})

@help.handle()
async def _(bot, event):
    await help.send('http://bot.shewinder.win')