import asyncio
import random
import time
from collections import defaultdict

from peewee import IntegrityError

from hoshino import Bot, Event, Service
from hoshino import permission
from hoshino.permission import ADMIN
from hoshino.typing import T_State
from .data import *
from .practice import PracticeManager, SignUpRecordManager
from .user import UserManager
from .exception import UserError

# 初始化数据库
db_file = 'data/db/expedition.db'
init(db_file)

sv = Service('早训助手')

pub = sv.on_command('publish practice', 
                    aliases={'发布早训', '发起早训'}, 
                    only_group=False, 
                    permission=ADMIN)

@pub.handle()
async def _(bot: Bot, event: Event, state: T_State):
    args = str(event.get_message()).strip()
    if args:
        state['title'] = args
@pub.got('title', prompt='请发送标题')
async def publish_practice(bot: Bot, event: Event, state: T_State):
    pass

@pub.got('content', prompt='请发送早训信息')
async def _(bot: Bot, event: Event, state: T_State):
    title = state['title']
    cont = state['content']
    pub_id = event.get_user_id()
    try:
        prt = Practice.create(id_=time.time(), publish_id=pub_id, title=title, content=cont)
        sv.logger.info(f'成功创建早训, 内容为{prt.content}')
        await pub.send(f'成功创建早训, 内容为{prt.content}')
    except Exception as e:
        sv.logger.exception(e)

#@pub.got('notice_time', prompt='请选择提醒时间，示例格式“03-11-23-30”')
async def _(bot: Bot, event: Event, state: T_State):
    time_str = state['notice_time']
    sv.logger.info(f'notice time is {time_str}')
    # TODO

async def judge_exist(bot: Bot, event: Event, state: T_State):
    # 判断当前是否存在正在进行的早训
    prts = PracticeManager.get_current_practice()
    if not prts:
        await show.finish('当前没有正在进行的早训') 
    if len(prts) == 1:
        state['which'] = 0
    else:
        prt_titles = [f'{i}:  {prt.title}' for i, prt in enumerate(prts)]
        await signup.send('以下为所有的早训,发送对应序号选择\n' + '\n'.join(prt_titles))      
    state['prts'] = prts  

async def choose_practice(bot: Bot, event: Event, state: T_State): 
    try:
        index = int(state['which'])
        state['prt'] = state['prts'][index]
    except IndexError:
        await bot.send(event, '输入超限!')
    except:
        await bot.send(event, '输入不合法, 请输入正确的序号')



deadline = sv.on_command('deadline', 
                    aliases={'报名截止', '截止报名'}, 
                    only_group=False, 
                    permission=ADMIN)
@deadline.handle()
async def _(bot: Bot, event: Event, state: T_State):
    # 判断当前是否存在正在进行的早训
    prts = PracticeManager.get_current_practice()
    if not prts:
        await show.finish('当前没有正在进行的早训') 
    if len(prts) == 1:
        state['which'] = 0
    else:
        prt_titles = [f'{i}:  {prt.title}' for i, prt in enumerate(prts)]
        await signup.send('以下为所有的早训,发送对应序号选择\n' + '\n'.join(prt_titles))      
    state['prts'] = prts                    
@deadline.got('which')
async def _(bot: Bot, event: Event, state: T_State): 
    try:
        index = int(state['which'])
        state['prt'] = state['prts'][index]
    except IndexError:
        await bot.send(event, '输入超限!')
    except:
        await bot.send(event, '输入不合法, 请输入正确的序号')
@deadline.handle()
async def _(bot: Bot, event: Event, state: T_State):
    prt = state['prt']
    try: 
        prt.status = 1
        prt.save()
        await deadline.send('早训报名已经截至')
        # 群里通知
    except Exception as e:
        sv.logger.exception(e) 


cancel = sv.on_command('cancel practice', 
                        aliases={'取消早训'}, 
                        only_group=False, 
                        permission=ADMIN)
@cancel.handle()
async def _(bot: Bot, event: Event, state: T_State):
    # 判断当前是否存在正在进行的早训
    prts = PracticeManager.get_current_practice()
    if not prts:
        await show.finish('当前没有正在进行的早训') 
    if len(prts) == 1:
        state['which'] = 0
    else:
        prt_titles = [f'{i}:  {prt.title}' for i, prt in enumerate(prts)]
        await signup.send('以下为所有的早训,发送对应序号选择\n' + '\n'.join(prt_titles))      
    state['prts'] = prts                    
@cancel.got('which')
async def _(bot: Bot, event: Event, state: T_State): 
    try:
        index = int(state['which'])
        state['prt'] = state['prts'][index]
    except IndexError:
        await bot.send(event, '输入超限!')
    except:
        await bot.send(event, '输入不合法, 请输入正确的序号')
@cancel.got('notice', prompt='是否私聊通知报名成员?')
async def cancel_practice(bot: Bot, event: Event, state: T_State):
    prt = state['prt']

    # 私聊通知报名成员
    notice = state['notice']
    if notice == '是' or notice == 'Y':
        try:
            pub_name = UserManager.get_name_by_qqid(prt.publish_id)
        except UserError as e:
            sv.logger.exception(e)
            await cancel.send(str(e))
        recs = SignUpRecordManager.get_signup_records(prt.id_)
        for rec in recs:
            qqid = rec.uid
            await bot.send_private_msg(user_id=qqid, 
                                       message=f'由{pub_name}于{prt.publish_time}发起的早训已经被取消')
            await asyncio.sleep(0.5)

    # 清空报名信息
    query = SignUpRecord.delete().where(SignUpRecord.practice_id==prt.id_)
    signup_num = query.execute()
    sv.logger.info(f'删除{signup_num}条报名记录')

    # 删除当前的早训计划
    practice_num = prt.delete_instance()
    sv.logger.info(f'删除{practice_num}条早训记录')
    await cancel.finish(f'成功取消早训,并清除{signup_num}条报名信息')

    # 删除当前的早训提醒

    

signup = sv.on_command('sign up', aliases={'报名早训', '报名'}, only_group=False)
@signup.handle()
async def _(bot: Bot, event: Event, state: T_State):
    # 判断当前是否存在正在进行的早训
    prts = PracticeManager.get_current_practice()
    if not prts:
        await signup.finish('当前没有正在进行的早训')
    prt_titles = [f'{i}:  {prt.title}' for i, prt in enumerate(prts)]
    await signup.send('以下为所有的早训,发送对应序号选择\n' + '\n'.join(prt_titles))
    state['prts'] = prts
@signup.got('which')
async def _(bot: Bot, event: Event, state: T_State):
    try:
        index = int(state['which'])
    except:
        await signup.send('输入不合法, 请输入正确的序号')
    prt = state['prts'][index]
    # 判断是否已经报名
    qqid = event.get_user_id()
    rec = SignUpRecord.get_or_none(uid=qqid, practice_id=prt.id_)
    if not rec is None:
        await signup.finish('您已经报名了,无需重复报名')

    # 判断是否已经截至
    if prt.status == 1:
        await signup.finish('报名已经截至，下次请早点来吧~')

    # 添加报名记录 是否通知管理者待定
    try:
        sign_name = UserManager.get_name_by_qqid(qqid)
    except UserError:
        sv.logger.exception(f'{qqid} try to signup without binding name with qq')
        await signup.finish('无法获取用户名,请先发送命令 绑定+空格+姓名绑定')

    try:
        SignUpRecord.create(uid=qqid, name=sign_name, practice_id=prt.id_)
        await signup.send(f'报名成功, 训练内容为{prt.content}')
    except Exception as e:
        sv.logger.exception(f'{e} exception occured when signing up')

cancel_signup = sv.on_command('cancel sign up', aliases={'取消报名'}, only_group=False)


bind = sv.on_command('bind', aliases={'绑定', '绑定QQ'}, only_group=False)
@bind.handle()
async def _(bot: Bot, event: Event, state: T_State):
    args = str(event.get_message()).strip()
    if args:
        state['name'] = args
@bind.got('name', prompt='请发送真实姓名')
async def _(bot: Bot, event: Event, state: T_State):
    name = state['name']
    qqid = event.get_user_id()
    try:
        User.create(qqid=qqid, name=name)
        await bot.send(event, '绑定成功')
    except IntegrityError:
        await bind.finish('您已经绑定过QQ了')

show = sv.on_command('show signup', 
                     aliases={'查看报名', '查看报名人员', '查看报名名单'}, 
                     only_group=False, 
                     permission=ADMIN)
@show.handle()
async def _(bot: Bot, event: Event, state: T_State):
    # 判断当前是否存在正在进行的早训
    prts = PracticeManager.get_current_practice()
    if not prts:
        await show.finish('当前没有正在进行的早训') 
    if len(prts) == 1:
        state['which'] = 0
    else:
        prt_titles = [f'{i}:  {prt.title}' for i, prt in enumerate(prts)]
        await signup.send('以下为所有的早训,发送对应序号选择\n' + '\n'.join(prt_titles))      
    state['prts'] = prts
@show.got('which')
async def _(bot: Bot, event: Event, state: T_State): 
    try:
        index = int(state['which'])
        prt = state['prts'][index]
    except IndexError:
        await show.send('输入超限!')
    except:
        await show.send('输入不合法, 请输入正确的序号')
    # 获取报名人员
    recs = SignUpRecordManager.get_signup_records(prt.id_)
    if not recs:
        await show.finish('还没有人报名')
    reply = [f'本次早训共{len(recs)}人报名']
    for rec in recs:
        qqid = rec.uid
        name = UserManager.get_name_by_qqid(qqid)
        reply.append(name)
    # 考虑到报名人数可能很多，可以用网页发送长消息
    if len(reply) < 30:
        await show.send('\n'.join(reply))
    else:
        await show.send('人数过多，请在网页上查看\nhttp://140.143.122.138:9000/too_long_show')
        pass

show_prt = sv.on_command('show practice', aliases={'查看早训', '查看训练'}, only_group=False)
@show_prt.handle()
async def _(bot: Bot, event: Event, state: T_State):
    # 判断当前是否存在正在进行的早训
    _status_dic = {0: '报名阶段', 1: '截止报名', 2: '签到中', 10: '归档'}
    prts = PracticeManager.get_current_practice()
    if not prts:
        await show.finish('当前没有正在进行的早训') 
    reply = ['早训列表:']
    for i, prt in enumerate(prts):
        reply.append(f'{i}: {prt.title} {_status_dic[prt.status]}')
    await bot.send(event, '\n'.join(reply))

alter = sv.on_command('alter', 
                      aliases={'修改早训内容', '修改内容', '修改早训', '修改'}, 
                      only_group=False, 
                      permission=ADMIN)

@alter.handle()
async def _(bot: Bot, event: Event, state: T_State):
    # 判断当前是否存在正在进行的早训
    prts = PracticeManager.get_current_practice()
    if not prts:
        await show.finish('当前没有正在进行的早训') 
    if len(prts) == 1:
        state['which'] = 0
    else:
        prt_titles = [f'{i}:  {prt.title}' for i, prt in enumerate(prts)]
        await signup.send('以下为所有的早训,发送对应序号选择\n' + '\n'.join(prt_titles))      
    state['prts'] = prts                    
@alter.got('which')
async def _(bot: Bot, event: Event, state: T_State): 
    try:
        index = int(state['which'])
        state['prt'] = state['prts'][index]
    except IndexError:
        await bot.send(event, '输入超限!')
    except:
        await bot.send(event, '输入不合法, 请输入正确的序号')
@alter.got('content', prompt='请发送要修改的内容')
async def _(bot: Bot, event: Event, state: T_State):
    # 判断当前是否存在正在进行的早训
    prt = state['prt']
    cont = state['content']
    try:
        prt.content = cont
        prt.save()
    except Exception as e:
        sv.logger.exception(e)
    state['content'] = cont

@alter.got('notice', prompt='是否私聊报名成员？')
async def _(bot: Bot, event: Event, state: T_State):
    notice = state['notice']
    prt = state['prt']
    cont = state['content']
    if notice == '是' or notice == 'Y':
        try:
            pub_name = UserManager.get_name_by_qqid(prt.publish_id)
        except UserError as e:
            sv.logger.exception(e)
            await cancel.send(str(e))
        recs = SignUpRecordManager.get_signup_records(prt.id_)
        for rec in recs:
            qqid = rec.uid
            await bot.send_private_msg(user_id=qqid, 
                                        message=f'由{pub_name}于{prt.publish_time}发起的早训内容被修改，以下为修改后内容：\n{cont}')
            await asyncio.sleep(0.5)

start_checkin = sv.on_command('start check', 
                              aliases={'开启签到', '开启打卡', '开始打卡', '开始签到'}, 
                              only_group=False, 
                              permission=ADMIN)
@start_checkin.handle()
async def _(bot: Bot, event: Event, state: T_State):
    # 判断当前是否存在正在进行的早训
    prts = PracticeManager.get_current_practice()
    if not prts:
        await show.finish('当前没有正在进行的早训') 
    if len(prts) == 1:
        state['which'] = 0
    else:
        prt_titles = [f'{i}:  {prt.title}' for i, prt in enumerate(prts)]
        await signup.send('以下为所有的早训,发送对应序号选择\n' + '\n'.join(prt_titles))      
    state['prts'] = prts                    
@start_checkin.got('which')
async def _(bot: Bot, event: Event, state: T_State): 
    try:
        index = int(state['which'])
        state['prt'] = state['prts'][index]
    except IndexError:
        await bot.send(event, '输入超限!')
    except:
        await bot.send(event, '输入不合法, 请输入正确的序号')

@start_checkin.handle()
async def _(bot: Bot, event: Event, state: T_State):
    prt = state['prt']
    prt.status = 2 # 设置状态为签到环节
    _token = ''
    for i in range(6):
        _token += random.choice('0123456789')
    prt.token = _token
    prt.save()
    await bot.send_private_msg(user_id=event.get_user_id(), message=f'本次签到口令为{_token}')

"""     # 如果管理忘记结束签到，5分组后自动结算
    await asyncio.sleep(300) 
    global _checkins
    try:
        prt.status = 10 # practice状态设置结束
        prt.save()
    except Exception as e:
        sv.logger.exception(e)
    for chk in _checkins:
        try:
            chk.save()
        except Exception as e:
            sv.logger.exception(e)
    await bot.send_private_msg(user_id=event.get_user_id(), message=f'自动结束签到') """
            
_checkins = defaultdict(list)
checkin = sv.on_command('check in', aliases={'签到', '打卡'}, only_group= False)
@checkin.handle()
async def _(bot: Bot, event: Event, state: T_State):
    # 判断当前是否存在正在进行的早训
    prts = PracticeManager.get_practice_by_status(2)
    if not prts:
        await show.finish('当前没有正在签到的早训') 
    if len(prts) == 1:
        state['which'] = 0
    else:
        prt_titles = [f'{i}:  {prt.title}' for i, prt in enumerate(prts)]
        await signup.send('以下为所有的早训,发送对应序号选择\n' + '\n'.join(prt_titles))      
    state['prts'] = prts                    
@checkin.got('which')
async def _(bot: Bot, event: Event, state: T_State): 
    try:
        index = int(state['which'])
        state['prt'] = state['prts'][index]
    except IndexError:
        await bot.send(event, '输入超限!')
    except:
        await bot.send(event, '输入不合法, 请输入正确的序号')

@checkin.got('token', prompt='请输入本次签到口令')
async def _(bot: Bot, event: Event, state: T_State):
    prt = state['prt']
    token = state['token']
    if token != prt.token:
        await checkin.reject('口令错误, 请重新输入')

    #判断是否报名
    qqid = int(event.get_user_id())
    if not SignUpRecordManager.is_signed(qqid=qqid, practice_id=prt.id_):
        await checkin.finish('您未报名，如特殊情况，请让管理人员代签')

    try:
        chk_name = UserManager.get_name_by_qqid(qqid)
    except UserError:
        sv.logger.exception(f'{qqid} try to check in  without binding name with qq')
        await signup.finish('无法获取用户名')
    global _checkins
    for chk in _checkins[prt.id_]:
        if chk.uid == qqid:
            await checkin.finish('已经签到过了')
            break
    try:
        chk_rec = CheckInRecord(uid=qqid, name=chk_name, practice_id=prt.id_)
        _checkins[prt.id_].append(chk_rec)
        await checkin.send('成功签到')
    except Exception as e:
        sv.logger.exception(e)

end_checkin = sv.on_command('end check', 
                              aliases={'结束签到', '结束打卡', '停止签到', '停止打卡'}, 
                              only_group=False, 
                              permission=ADMIN)
@end_checkin.handle()
async def _(bot: Bot, event: Event, state: T_State):
    # 判断当前是否存在正在进行的早训
    prts = PracticeManager.get_practice_by_status(2)
    if not prts:
        await show.finish('当前没有正在签到的早训') 
    if len(prts) == 1:
        state['which'] = 0
    else:
        prt_titles = [f'{i}:  {prt.title}' for i, prt in enumerate(prts)]
        await signup.send('以下为所有的早训,发送对应序号选择\n' + '\n'.join(prt_titles))      
    state['prts'] = prts                    
@end_checkin.got('which')
async def _(bot: Bot, event: Event, state: T_State): 
    try:
        index = int(state['which'])
        state['prt'] = state['prts'][index]
    except IndexError:
        await bot.send(event, '输入超限!')
    except:
        await bot.send(event, '输入不合法, 请输入正确的序号')

@end_checkin.handle()
async def _(bot: Bot, event: Event, state: T_State):
    prt = state['prt']
    if prt.status != 2:
        await end_checkin.finish('请先开启签到')

    # 确认签到表,有误则重新签到
    recs = SignUpRecordManager.get_signup_records(prt.id_)
    reply = [f'本次早训共{len(recs)}人报名']
    checkin_num = len(_checkins[prt.id_])
    reply.append(f'实际打卡{checkin_num}人, 鸽子{len(recs) - checkin_num}人如下')
    for sign_rec in recs:
        check_flag = False
        for chk in _checkins[prt.id_]:
            if sign_rec.uid == chk.uid: # 判断已经打卡
                check_flag = True
                break
        if not check_flag:
            name = sign_rec.name
            reply.append(name)
    await end_checkin.send('\n'.join(reply))

@end_checkin.got('confirm', prompt='请校对签到情况是否正确,发送是|否|取消')    
async def _(bot: Bot, event: Event, state: T_State):
    confirm = state['confirm']
    prt = state['prt']
    global _checkins
    if confirm == '是':
        # 早训记录归档
        for chk in _checkins[prt.id_]:
            try:
                sv.logger.info(f'saving check in record of {chk.name}')

                chk.save(force_insert = True) # I dont know why force_insert must be used here
                sv.logger.info(f'saved check in record of {chk.name}')
            except Exception as e:
                sv.logger.exception(e)
        del _checkins[prt.id_]
        prt.status = 10
        prt.save()
        await end_checkin.send('本次早训已归档')
    elif confirm == '否':
        del _checkins[prt.id_]
        prt.status = 1
        prt.save()
        await end_checkin.send('本次签到取消,请重新签到')
    else:
        pass 

bc = sv.on_command('broadcast', aliases={'广播'}, only_group=False, permission=ADMIN)
@bc.handle()
async def _(bot: Bot, event: Event, state: T_State):
    # 判断当前是否存在正在进行的早训
    prts = PracticeManager.get_current_practice()
    if not prts:
        await show.finish('当前没有正在进行的早训') 
    if len(prts) == 1:
        state['which'] = 0
    else:
        prt_titles = [f'{i}:  {prt.title}' for i, prt in enumerate(prts)]
        await signup.send('以下为所有的早训,发送对应序号选择\n' + '\n'.join(prt_titles))      
    state['prts'] = prts                    
@bc.got('which')
async def _(bot: Bot, event: Event, state: T_State): 
    try:
        index = int(state['which'])
        state['prt'] = state['prts'][index]
    except IndexError:
        await bot.send(event, '输入超限!')
    except:
        await bot.send(event, '输入不合法, 请输入正确的序号')
@bc.got('content', prompt='请发送要广播的内容')
async def _(bot: Bot, event: Event, state: T_State):
    prt = state['prt']
    cont = state['content']
    signups = SignUpRecordManager.get_signup_records(prt.id_)
    name = UserManager.get_name_by_qqid(int(event.get_user_id()))
    for i in signups:
        try:
            await bot.send_private_msg(user_id=i.uid, message=f'您收到来自{name}的温馨提醒：\n{cont}')
            await asyncio.sleep(0.5)
        except Exception as e:
            sv.logger.exception(e)
    sv.logger.info(f'共投递{len(signups)}条消息')

help = sv.on_command('help', aliases={'帮助', '帮助手册'}, only_group=False)
@help.handle()
async def _(bot: Bot, event: Event, state: T_State):
    await help.send('http://140.143.122.138:9000/help')

repr_checkin = sv.on_command('check in', aliases={'代签到', '代签'}, only_group= False, permission=ADMIN)
@repr_checkin.handle()
async def _(bot: Bot, event: Event, state: T_State):
    # 判断当前是否存在正在进行的早训
    prts = PracticeManager.get_practice_by_status(2)
    if not prts:
        await show.finish('当前没有正在签到的早训') 
    if len(prts) == 1:
        state['which'] = 0
    else:
        prt_titles = [f'{i}:  {prt.title}' for i, prt in enumerate(prts)]
        await signup.send('以下为所有的早训,发送对应序号选择\n' + '\n'.join(prt_titles))      
    state['prts'] = prts                    
@repr_checkin.got('which')
async def _(bot: Bot, event: Event, state: T_State): 
    try:
        index = int(state['which'])
        state['prt'] = state['prts'][index]
    except IndexError:
        await bot.send(event, '输入超限!')
    except:
        await bot.send(event, '输入不合法, 请输入正确的序号')
@repr_checkin.got('qqid', prompt='请输入代签的qq号， 空格分开')
async def _(bot: Bot, event: Event, state: T_State): 
    prt = state['prt']
    qq_str = state['qqid']
    qqids = qq_str.split()
    for qqid in qqids:
        try:
            qqid = int(qqid)
        except:
            await bot.send(event, '输入不合法')
        try:
            chk_name = UserManager.get_name_by_qqid(qqid)
        except UserError:
            sv.logger.exception(f'{qqid} try to check in  without binding name with qq')
            await signup.finish('无法获取用户名')
        global _checkins
        for chk in _checkins[prt.id_]:
            if chk.uid == qqid:
                await checkin.finish('已经签到过了')
                break
        try:
            chk_rec = CheckInRecord(uid=qqid, name=chk_name, practice_id=prt.id_)
            _checkins[prt.id_].append(chk_rec)
            await checkin.send('成功签到')
        except Exception as e:
            sv.logger.exception(e)
