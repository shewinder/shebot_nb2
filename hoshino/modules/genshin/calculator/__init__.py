from pathlib import Path
from typing import List

import aiohttp
from loguru import logger
from nonebot.adapters.cqhttp.event import MessageEvent
from nonebot.typing import T_State

from hoshino import Service, Bot
from hoshino.sres import Res as R
from hoshino.util.sutil import extract_url_from_event, load_config, save_config
from hoshino.util import pic2b64
from .model import Chara, Artifact, Weapon
from .ocr_artifact import artifact_from_ocr
from .config import USER_CHARA_DIR, USER_ART_DIR, USER_DIR
from .dmg_calc import CALCULATORS, BaseDMGCalculator
from .util import get_user_chara, get_user_artset, get_user_ysid
from .ysinfo import get_chara_from_miyoushe, get_ysinfo


sv = Service('原神伤害')

add_chara = sv.on_command('add chara', aliases={'添加角色'})

supported = ['胡桃', '甘雨', '宵宫']

@add_chara.handle()
async def add_character(bot: Bot, event: MessageEvent, state: T_State):
    msg = str(event.get_message()).strip()
    if msg:
        state['name'] = msg

@add_chara.got('name', prompt=f'请输入角色名, 目前支持{supported}')
async def _(bot: Bot, event: MessageEvent, state: T_State):
    name = state['name']
    if name not in supported:
        #await add_chara.finish('暂时不支持该角色')
        pass

@add_chara.got('rank', prompt=f'请输入角色命座 0-6')
async def _(bot: Bot, event: MessageEvent, state: T_State):
    try:
        rank = int(state['rank'])
    except:
        await add_chara.finish('输入不合法')
    if rank > 6 or rank < 0:
        await add_chara.finish('输入不合法')
    state['rank'] = rank

@add_chara.got('level', prompt=f'请输入角色等级 1-90')
async def _(bot: Bot, event: MessageEvent, state: T_State):
    try:
        level = int(state['level'])
    except:
        await add_chara.finish('输入不合法')
    if level > 90 or level < 1:
        await add_chara.finish('输入不合法')
    state['level'] = level

@add_chara.got('weapon', prompt=f'请输入武器名等级和精炼等级,空格分隔')
async def _(bot: Bot, event: MessageEvent, state: T_State):
    try:
        w = state['weapon'].split(' ')[0]
        level = int(state['weapon'].split(' ')[1])
        refinement = int(state['weapon'].split(' ')[2])
    except:
        await add_chara.reject('输入不合法') 

    if refinement > 5 or refinement < 0:
        await add_chara.finish('精炼等级不合法')
    state['weapon'] = w
    state['refinement'] = refinement
    weapon = Weapon.create(w, refinement, level)
    state['weapon'] = weapon

@add_chara.got('talent', prompt=f'请输入天赋等级,空格分隔')
async def _(bot: Bot, event: MessageEvent, state: T_State):
    try:
        a = state['talent'].strip().split(' ')
        t1 = int(a[0])
        t2 = int(a[1])
        t3 = int(a[2])
    except:
        await add_chara.finish('输入不合法') 
    
    chara: Chara = Chara.create(state['name'], state['rank'], state['level'], state['weapon'], t1, t2, t3)

    uid = event.user_id
    user_chara_path = USER_CHARA_DIR.joinpath(f'{uid}.json')
    if not user_chara_path.exists():
        user_chara_path.touch()
    chara.save_to_file(user_chara_path)
    await add_chara.send('添加成功')

    
add_artifacts = sv.on_command('add artifacts', aliases={'添加圣遗物'})
@add_artifacts.handle()
async def _(bot: Bot, event: MessageEvent, state: T_State):
    uid = event.user_id
    user_chara_path = USER_CHARA_DIR.joinpath(f'{uid}.json')
    user_charas = load_config(user_chara_path)
    if not user_charas:
        await add_artifacts.finish('请先添加角色')
    charas = [f'{k} 'for  k in user_charas.keys()]
    state['user_charas'] = user_charas
    await add_artifacts.send('请先发送角色名\n'+ '\n'.join(charas))

@add_artifacts.got('name')
async def _(bot: Bot, event: MessageEvent, state: T_State):
    name = state['name']
    user_charas = state['user_charas']
    chara_dict = user_charas.get(name)
    if not chara_dict:
        await add_artifacts.reject('不存在的角色')
    chara = Chara(**chara_dict)
    state['chara'] = chara

@add_artifacts.got('urls', prompt='请发送截图，建议一次发一张')
async def _(bot: Bot, event: MessageEvent, state: T_State):
    chara: Chara = state['chara']
    arts = []
    ocp = []
    msg = event.get_message()
    for m in msg:
        if m.type == 'image':
            ocr = await bot.call_api('ocr_image', image=m['data']['file'])
            art = artifact_from_ocr(ocr)
            if art:
                if chara.art_set.occupied(art):
                    ocp.append(art)
                arts.append(art)
        t = '\n'.join([str(art)+'\n' for art in arts])

    if ocp:
        temp = [i.ch for i in ocp]
        s = ','.join(temp)
        await add_artifacts.send(f'识别到如下结果{t}\n'+ f'warning: {s}位置已经装备了圣遗物,是否添加\n')
    else:
        await add_artifacts.send(f'识别到如下结果，是否添加\n{t}')
    state ['arts'] = arts


    #urls = extract_url_from_event(event)
    #chara: Chara = state['chara']
    #arts = []
    #ocp = []
    #for url in urls:
    #    async with  aiohttp.ClientSession() as session:
    #        async with session.get(url) as resp:
    #            cont = await resp.read()
    #    try:
    #        art = artifact_from_screenshot(cont)
    #    except Exception as e:
    #        logger.exception(e)
    #        await add_artifacts.finish('识别失败')
    #    if art:
    #        if chara.art_set.occupied(art):
    #            ocp.append(art)
    #        arts.append(art)
    #
    #t = '\n'.join([str(art) for art in arts])
    #
    #if ocp:
    #    temp = [i.ch for i in ocp]
    #    s = ','.join(temp)
    #    await add_artifacts.send(f'识别到如下结果，且{s}位置已经装备了圣遗物,是否添加\n{t}')
    #else:
    #    await add_artifacts.send(f'识别到如下结果，是否添加\n{t}')
    #state ['arts'] = arts

@add_artifacts.got('cfm')
async def _(bot: Bot, event: MessageEvent, state: T_State):  
    chara: Chara = state['chara']
    cfm = state['cfm'] 
    arts: List[Artifact] = state['arts']
    if cfm == 'Y' or cfm == 'y' or cfm == '是':
        for art in arts:
            chara.art_set.add(art)
        uid = event.user_id
        chara.save_to_file(USER_CHARA_DIR.joinpath(f'{uid}.json'))
        await add_artifacts.send('添加成功')
    else:
        await add_artifacts.send('已取消')

calc = sv.on_command('伤害计算')

@calc.handle()
async def _(bot: Bot, event: MessageEvent, state: T_State):  
    a = [f'{i+1}. {c.keyword}' for i,c in enumerate(CALCULATORS)]
    await calc.send(f'请选择计算模板\n' + '\n'.join(a))

@calc.got('choice')
async def _(bot: Bot, event: MessageEvent, state: T_State):  
    try:
        choice = int(state['choice']) - 1
    except:
        await calc.finish('输入不合法')
    calculator: BaseDMGCalculator = CALCULATORS[choice]
    chara = get_user_chara(event.user_id, calculator.chara_name)
    if not chara:
        await calc.finish('还未添加该角色,请先发送“添加角色”')
    await calc.send(calculator.get_result(chara))
        
save_arts = sv.on_command('导出圣遗物')

@save_arts.got('name', prompt='请选择角色')
async def _(bot: Bot, event: MessageEvent, state: T_State):  
    chara_name = state['name']
    chara: Chara = get_user_chara(event.user_id, chara_name)
    if not chara:
        await save_arts.finish('未添加该角色，请先添加角色')
    if chara.art_set.count() < 4:
        await save_arts.finish('该角色穿戴圣遗物过少')
    state['chara'] = chara 

@save_arts.got('save_name', prompt='请选择保存名字，不能全为数字')
async def _(bot: Bot, event: MessageEvent, state: T_State):  
    save_name = state['save_name']
    chara: Chara = state['chara']
    chara.art_set.save_to_file(USER_ART_DIR.joinpath(f'{event.user_id}.json'), save_name)
    await save_arts.send('保存成功')

load_arts = sv.on_command('save arts', aliases={'导入圣遗物'})

@load_arts.got('name', prompt='请选择角色')
async def _(bot: Bot, event: MessageEvent, state: T_State):  
    chara_name = state['name']
    chara: Chara = get_user_chara(event.user_id, chara_name)
    if not chara:
        await save_arts.finish('未添加该角色，请先添加角色')
    if chara.art_set.count() < 4:
        await save_arts.finish('该角色穿戴圣遗物过少')
    state['chara'] = chara 

    arts_dic = load_config(USER_ART_DIR.joinpath(f'{event.user_id}.json'))
    a = [k for k in arts_dic]
    await load_arts.send('请选择套装名\n'+'\n'.join(a))

@load_arts.got('art_name')
async def _(bot: Bot, event: MessageEvent, state: T_State):  
    art_name = state['art_name']
    artset = get_user_artset(event.user_id, art_name)
    if not artset:
        await load_arts.reject('不存在的圣遗物套装,请重新发送')
    chara: Chara = state['chara']
    chara.art_set = artset
    uid = event.user_id
    chara.save_to_file(USER_CHARA_DIR.joinpath(f'{uid}.json'))
    await load_arts.send('导入成功')


bind = sv.on_command('绑定')

@bind.handle()
async def _(bot: Bot, event: MessageEvent, state: T_State):  
    ysid = str(event.get_message()).strip()
    if ysid:
        state['ysid'] = ysid

@bind.got('ysid', prompt='请发送原神id')   
async def _(bot: Bot, event: MessageEvent, state: T_State):  
    ysid = state['ysid']
    """try:
        data = get_ysinfo(uid = ysid)
        if data['retcode'] != 0:
            await bind.finish(f'未查询到信息, 请确定绑定米游社')
    except Exception as e:
        await bind.finish(e)"""
    p = USER_DIR.joinpath('binds.json')
    if not p.exists():
        p.touch()
    c = load_config(p)
    c[str(event.user_id)] = ysid
    save_config(c, p)
    await bind.send('绑定成功')

load_chara = sv.on_command('米游社导入', aliases={'导入角色'})

@load_chara.handle()
async def _(bot: Bot, event: MessageEvent, state: T_State):  
    if not get_user_ysid(event.user_id):
        await load_chara.finish('请先绑定原神uid')
    chara_name = str(event.get_message()).strip()
    if chara_name:
        state['chara_name'] = chara_name

@load_chara.got('chara_name', prompt='请发送原神角色名')   
async def _(bot: Bot, event: MessageEvent, state: T_State):  
    pass
    
@load_chara.got('talent', prompt=f'请输入天赋等级,空格分隔')
async def _(bot: Bot, event: MessageEvent, state: T_State):
    try:
        a = state['talent'].strip().split(' ')
        t1 = int(a[0])
        t2 = int(a[1])
        t3 = int(a[2])
    except:
        await add_chara.finish('输入不合法') 
    
    cname = state['chara_name']
    try:
        chara_dic = get_chara_from_miyoushe(get_user_ysid(event.user_id), cname)
    except Exception as e:
        logger.exception(e)
        await load_chara.send('查询信息异常')
    weapon = Weapon.create(chara_dic['w_name'], chara_dic['refine'], chara_dic['w_level'])
    
    chara: Chara = Chara.create(cname, chara_dic['rank'], chara_dic['c_level'], weapon, t1, t2, t3)
    p = USER_CHARA_DIR.joinpath(f'{event.user_id}.json')
    if not p.exists():
        p.touch()
    chara.save_to_file(p)
    await load_chara.send('导入成功')

        


    

    
        






