from pydantic.main import BaseModel
from .model import Artifact, Attr, Chara, Chara, DMGEnum
from .weapon_effect import WEAPON_EFFECT
from .set_bonus import get_set2_names, get_set4_name, SET4_BONUS, SET2_BONUS
from .target import Target

class Hit(BaseModel):
    type_: DMGEnum = DMGEnum.hit
    elem: str = None 
    rate: float = 0 # 倍率

def get_total_attr(chara: Chara, buff: Attr=Attr()) -> Attr:
    w = chara.weapon
    artifacts = chara.art_set.sum()
    print(artifacts)
    print(chara.attr)
    s: Attr = chara.attr + artifacts.attr + w.attr + buff # 人物自带属性加武器属性加上圣遗物属性

    # 计算武器特效
    WEAPON_EFFECT.get(w.name)(w.refinement, s)

    # 计算圣遗物4件套
    set_ = chara.art_set
    name = get_set4_name(set_.flower, set_.plume, set_.sand, set_.goblet, set_.circlet)
    if name:
        SET4_BONUS.get(name)(chara, s)
    
    # 计算圣遗物2件套, 4件套返回空
    for name in get_set2_names(set_.flower, set_.plume, set_.sand, set_.goblet, set_.circlet):
        s += SET2_BONUS.get(name)

    # 计算buff
    s += buff

    attr = s
    print(chara.baseATK)
    print(w.baseATK)
    print(s.ATK_bonus)
    attr.ATK = (chara.baseATK + w.baseATK) * (1 + s.ATK_bonus)  + s.ATK
    attr.HP = chara.baseHP * (1 + s.HP_bonus) + s.HP
    attr.DEF = chara.baseDEF * (1+ s.DEF_bonus) + s.DEF

    return attr

def get_dmg(c: Chara, attr: Attr, hit: Hit, t: Target, melt=False, vaporize=False, crit=False, independent_cof=1):
    if hit.type_ == DMGEnum.hit:
        dmg_bonus = attr.hit_bonus + attr.dict().get(hit.elem)
    elif hit.type_ == DMGEnum.charged_atk:
        dmg_bonus = attr.charged_hit_bonus + attr.dict().get(hit.elem)
    elif hit.type_ == DMGEnum.elem_skill:
        dmg_bonus = attr.elem_skill_bonus + attr.dict().get(hit.elem)
    elif hit.type_ == DMGEnum.elem_burst:
        dmg_bonus = attr.elem_burst_bonus + attr.dict().get(hit.elem)
    else:
        raise ValueError('不存在的伤害类型')
    
    # 计算蒸发融化
    mastery_bonus = 25/9*attr.elem_mastery / (1400 + attr.elem_mastery)
    if melt:
        melt_cof = 2 * (1 + attr.melt_bonus + mastery_bonus) #按照实际伤害，猜测精通和魔女同属一个区间
    else:
        melt_cof = 1
    if vaporize:
        vaporize_cof = 1.5 * (1 + attr.vaporize_bonus + mastery_bonus)
    else:
        vaporize_cof = 1
    crit_cof = 1 + attr.crit_dmg if crit else 1

    #怪物抗性乘区
    if t.__dict__[hit.elem] <= 0:
        resist_cof = 1 - t.__dict__[hit.elem]/2
    elif t.__dict__[hit.elem] <= 0.75:
        resist_cof  = 1 - t.__dict__[hit.elem]
    elif t.__dict__[hit.elem] <= 1:
        resist_cof = 1 / (1 + t.__dict__[hit.elem]*4)
    else:
        raise ValueError('目标抗性范围不能大于1')  

    # 怪物防御力乘区
    #target_def_cof = (c.level + 100) / ((1 - attr.DEF_decrease)*(t.level + 100) + c.level + 100)
    t_def = (t.level * 5 + 500) * (1 - attr.DEF_decrease) 
    target_def_cof = (c.level * 5 + 500) / (t_def + c.level*5 + 500)

    print('攻击力', attr.ATK, '倍率', hit.rate, '暴击系数', crit_cof, '伤害加成系数', (1+dmg_bonus), '蒸发系数', vaporize_cof, '融化系数', melt_cof, '目标抗性系数', resist_cof, '目标防御力系数', target_def_cof, '独立系数', independent_cof)
    dmg = attr.ATK * hit.rate * crit_cof * (1 + dmg_bonus) * vaporize_cof * melt_cof  * resist_cof * target_def_cof * independent_cof
    print(dmg)
    return dmg