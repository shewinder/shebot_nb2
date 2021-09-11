
from .model import Attr
from typing import Callable


WEAPON_EFFECT = {}
def add_weapon(name: str):
    def deco(func: Callable):
        WEAPON_EFFECT[name] = func
    return deco

@add_weapon('决斗之枪')
def _(refine: int, attr: Attr, **kwargs):
    """
    只考虑单个敌人情况
    """
    attr.ATK_bonus += 0.24 + 0.06*(refine - 1)

@add_weapon('天空之翼')
def _(refine: int, attr: Attr, **kwargs):
    attr.crit_dmg += 0.2 + 0.05*(refine - 1)

@add_weapon('天空之翼')
def _(refine: int, attr: Attr, **kwargs):
    attr.crit_dmg += 0.2 + 0.05*(refine - 1)

@add_weapon('西风长枪')
def _(refine: int, attr: Attr, **kwargs):
    pass # 笑死，没伤害

@add_weapon('薙草之稻光')
def _(refine: int, attr: Attr, **kwargs):
    """攻击力获得提升，提升程度相当于元素充能效率超出100%部分的28%/35%/42%/49%/56%，
    至多通过这种方式提升80%/90%/100%/110%/120%。施放元素爆发后的12秒内，
    元素充能效率提升30%/35%/40%/45%/50%。
    """
    attr.energy_recharge += 0.3 + 0.05*(refine - 1)
    bonus = (attr.energy_recharge - 1) * (0.28 + 0.07*(refine - 1))
    max = 0.8 + 0.1*(refine-1)
    if bonus > max:
        bonus = max
    attr.ATK_bonus += bonus