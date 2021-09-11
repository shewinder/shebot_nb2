import re
from typing import Dict

from .model import Attr, Artifact, ELemEnum

from .util import to_number, ocr
from .const import ENTS_FIX, ENTS_PER

entrys = ['生命值',
          '防御力',
          '攻击力',
          '火元素伤害加成',
          '水元素伤害加成',
          '冰元素伤害加成',
          '风元素伤害加成',
          '雷元素伤害加成',
          '岩元素伤害加成',
          '物理伤害加成',
          '元素充能效率',
          '暴击率',
          '暴击伤害',
          '元素精通']

artifacts_names = [
    '炽烈的炎之魔女',
    '角斗士的终幕礼',
    '绝缘之旗印',
    '追忆之注连',
    '冰风迷途的勇士',
    '染血的骑士道',
    '流浪大地的乐团',
    '苍白之火',
    '昔日宗室之仪'
]

""" def artifact_from_screenshot(img_bytes) -> Artifact:
    res = ocr(img_bytes)
    chs = ['生之花', '死之羽', '时之沙', '空之杯', '理之冠']
    engs = ['flower', 'plume', 'sand', 'goblet', 'circlet']
    flag1 = False
    flag2 = False
    for i,ch in enumerate(chs):
        if ch in str(res):
            flag1 = True
            break
    for name in artifacts_names:
        if name in str(res):
            flag2 = True
            break
    if not flag1 or not flag2:
        return None
    art = Artifact(type_=name, ch=ch, eng=engs[i])
    for i, r in enumerate(res):
        words = r['words'].strip('.').strip('·')
        for j in entrys:
            if words.startswith(j):
                n = words.strip(j)
                if not n: # 可能被识别到下一行
                    n = res[i+1]['words'].strip('.').strip('·')
                if '%' in n:
                    a = to_number(n)
                    if a > 0.7:
                        a /= 10
                    art.attr.__dict__[ENTS_PER[j]] = a
                else:
                    art.attr.__dict__[ENTS_FIX[j]] = to_number(n)
    return art """

def artifact_from_ocr(dic: Dict) -> Artifact:
    chs = ['生之花', '死之羽', '时之沙', '空之杯', '理之冠']
    engs = ['flower', 'plume', 'sand', 'goblet', 'circlet']
    flag1 = False
    flag2 = False
    for i,ch in enumerate(chs):
        if ch in str(dic):
            flag1 = True
            break
    for name in artifacts_names:
        if name in str(dic):
            flag2 = True
            break
    if not flag1 or not flag2:
        return None

    res = dic['texts']
    art = Artifact(type_=name, ch=ch, eng=engs[i])
    for i, r in enumerate(res):
        words = r['text'].strip('.').strip('·')
        for j in entrys:
            if words.startswith(j):
                n = words.strip(j)
                if not n: # 可能被识别到下一行
                    n = res[i+1]['text'].strip('.').strip('·')
                if '%' in n:
                    art.attr.__dict__[ENTS_PER[j]] = to_number(n)
                else:
                    art.attr.__dict__[ENTS_FIX[j]] = to_number(n)
    return art
                

