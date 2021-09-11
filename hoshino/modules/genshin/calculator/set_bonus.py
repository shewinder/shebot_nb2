from typing import Callable
from collections import defaultdict

from .model import Attr, Artifact, Chara
from .enums import WeaponTypeEnum

def get_set4_name(
        flower: Artifact,
        plume: Artifact,
        sand: Artifact,
        goblet: Artifact,
        circlet: Artifact):
    count = defaultdict(int)
    if flower.type_:
        count[flower.type_] += 1
    if plume.type_:
        count[plume.type_] += 1
    if sand.type_:
        count[sand.type_] += 1
    if goblet.type_:
        count[goblet.type_] += 1
    if circlet.type_:
        count[circlet.type_] += 1
    for k in count:
        if count[k] >= 4:
            return k
    return None

def get_set2_names(
        flower: Artifact,
        plume: Artifact,
        sand: Artifact,
        goblet: Artifact,
        circlet: Artifact):
    count = defaultdict(int)
    if flower.type_:
        count[flower.type_] += 1
    if plume.type_:
        count[plume.type_] += 1
    if sand.type_:
        count[sand.type_] += 1
    if goblet.type_:
        count[goblet.type_] += 1
    if circlet.type_:
        count[circlet.type_] += 1
    for k in count:
        if count[k] >= 4:
            return []

    set2 = []
    for k in count:
        if count[k] >= 2:
            set2.append(k)
    return set2

SET2_BONUS = {
    '炽烈的炎之魔女': Attr(pyro=0.15),
    '角斗士的终幕礼': Attr(ATK_bonus=0.18),
    '绝缘之旗印': Attr(energy_recharge=0.2),
    '追忆之注连': Attr(ATK_bonus=0.18),
    '冰风迷途的勇士': Attr(cryo=0.15),
    '染血的骑士道': Attr(physical=0.25),
    '流浪大地的乐团': Attr(elem_mastery=80),
    '苍白之火': Attr(physical=0.25),
    '昔日宗室之仪': Attr(elem_burst_bonus=0.2)
}

SET4_BONUS = {}
def add_set4(name: str):
    def deco(func: Callable):
        SET4_BONUS[name] = func
    return deco

@add_set4('炽烈的炎之魔女')
def _(chara, attr: Attr, **kwargs):
    s = kwargs.get('stacks', 1)
    attr.pyro += 0.15*(1 + 0.5*s)
    attr.vaporize_bonus += 0.15
    attr.melt_bonus += 0.15

@add_set4('流浪大地的乐团')
def _(chara: Chara, attr: Attr, **kwargs):
    # 弓箭和法器角色重击伤害增加35%
    attr.elem_mastery += 80
    if chara.type_ == WeaponTypeEnum.bow or chara.type_ == WeaponTypeEnum.book:
        attr.charged_hit_bonus += 0.35

@add_set4('追忆之注连')
def _(chara: Chara, attr: Attr, **kwargs):
    attr.ATK_bonus += 0.18
    attr.hit_bonus += 0.5
    attr.charged_hit_bonus += 0.5
    attr.plunge_hit_bonus += 0.5

@add_set4('绝缘之旗印')
def _(chara: Chara, attr: Attr, **kwargs):
    attr.energy_recharge += 0.2
    bonus = attr.energy_recharge * 0.25
    if bonus > 0.75:
        bonus = 0.75
    attr.elem_burst_bonus += bonus