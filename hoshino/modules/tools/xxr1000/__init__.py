from nonebot.typing import T_State
from peewee import fn

from hoshino import Service, Bot, Event
from .model import Quest

service = Service('肖秀荣')
qu = service.on_command('肖秀荣', aliases={'来道肖秀荣', '来道政治题', '来道考研政治'})
qu_mayuan = service.on_command('马原', aliases={'来道马原'})
qu_mzt = service.on_command('毛中特', aliases={'来道毛中特'})
qu_jds = service.on_command('近代史', aliases={'来道近代史'})
qu_sixiu = service.on_command('思修', aliases={'来道思修'})

def judge(str1, str2):
    return set(str1) == set(str2)

@qu.handle()
async def choose(bot: Bot, event: Event, state: T_State):
    qus: Quest = Quest.select().order_by(fn.Random()).limit(1)
    state['qus'] = qus[0]

@qu_mayuan.handle()
async def choose(bot: Bot, event: Event, state: T_State):
    qus: Quest = Quest.select().where(((Quest.Catalog == '马原单选') | 
    (Quest.Catalog == '马原多选'))).order_by(fn.Random()).limit(1)
    state['qus'] = qus[0]

@qu_mzt.handle()
async def choose(bot: Bot, event: Event, state: T_State):
    qus: Quest = Quest.select().where(((Quest.Catalog == '毛中特单选') | 
    (Quest.Catalog == '毛中特多选'))).order_by(fn.Random()).limit(1)
    state['qus'] = qus[0]

@qu_jds.handle()
async def choose(bot: Bot, event: Event, state: T_State):
    qus: Quest = Quest.select().where(((Quest.Catalog == '近代史纲要单选') | 
    (Quest.Catalog == '近代史纲要多选'))).order_by(fn.Random()).limit(1)
    state['qus'] = qus[0]

@qu_sixiu.handle()
async def choose(bot: Bot, event: Event, state: T_State):
    qus: Quest = Quest.select().where(((Quest.Catalog == '思修单选') | 
    (Quest.Catalog == '思修多选'))).order_by(fn.Random()).limit(1)
    state['qus'] = qus[0]

async def ques(bot: Bot, event: Event, state: T_State):
    qus: Quest = state['qus']
    type_ = '(单选)' if qus.Catalog.endswith('单选') else '(多选)'
    reply = [
        type_ + qus.Question,
        qus.OptionA,
        qus.OptionB,
        qus.OptionC,
        qus.OptionD,    
    ]
    await bot.send(event, '\n'.join(reply))

qu.handle()(ques)
qu_mayuan.handle()(ques)
qu_mzt.handle()(ques)
qu_jds.handle()(ques)
qu_sixiu.handle()(ques)

async def revise(bot: Bot, event: Event, state: T_State):
    qus: Quest = state['qus']
    ans = state['ans'].upper()
    if judge(qus.Answer, ans):
        await bot.send(event, '恭喜你，答对了！')
    else:
        await bot.send(event, f'很遗憾，答错了，答案是{qus.Answer}')

qu.got('ans')(revise)
qu_mayuan.got('ans')(revise)
qu_mzt.got('ans')(revise)
qu_jds.got('ans')(revise)
qu_sixiu.got('ans')(revise)



