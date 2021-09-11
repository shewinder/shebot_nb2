from typing import Callable, Dict
from pydantic import BaseModel

from .model import Chara, Attr
from .enums import DMGEnum, ELemEnum
from .calculate import get_total_attr, get_dmg, Hit
from .target import xiaobao, Target

class BaseDMGCalculator(BaseModel):
    keyword: str
    chara_name: str
    target: Target = xiaobao
    remarks: str = None

    def get_result(self, chara: Chara):
        raise NotImplementedError

CALCULATORS = []

def add_calculator(cls: Callable):
    CALCULATORS.append(cls())

@add_calculator
class Hutao(BaseDMGCalculator):
    chara_name: str = '胡桃'
    keyword: str = '胡桃重击'
    target: Target = xiaobao

    def get_result(self, chara: Chara):
        attr: Attr = get_total_attr(chara)
        trans = [0.0384, 0.0407, 0.043,	0.046,	0.0483,	0.0506,	0.0536,	0.0566,	0.0596,	0.0626,	0.0656,	0.0685, 0.0715]
        trans_cof = trans[chara.elem_skill_level-1]
        attr.ATK += attr.HP * trans_cof # 胡桃天赋
        attr.pyro += 0.33 # 血量低于50%
        hit = Hit(elem=ELemEnum.pyro, rate=self.get_rate(chara), type_=DMGEnum.charged_atk)
        print(attr)
        res = f"""
        攻击类型 {hit.type_}
        攻击目标 {self.target.name}
        重击伤害(暴击) {get_dmg(chara, attr, hit, self.target, crit=True)}
        重击伤害(暴击蒸发) {get_dmg(chara, attr, hit, self.target, vaporize=True, crit=True)}
        重击伤害(暴击融化) {get_dmg(chara, attr, hit, self.target, melt=True, crit=True)}
        """.strip()
        return res
    
    def get_rate(self, chara: Chara):
        rate = [1.36, 1.452, 1.545, 1.669, 1.761, 1.869, 2.009, 2.148, 2.287, 2.426, 2.565]
        return rate[chara.hit_level-1]

@add_calculator
class Ganyu(BaseDMGCalculator):
    chara_name = '甘雨'
    keyword: str = '甘雨蓄力'

    def get_result(self, chara: Chara):
        attr: Attr = get_total_attr(chara)
        if chara.rank >= 1:
            self.target.cryo -= 0.15 # 甘雨一命效果
        hit1 = Hit(elem=ELemEnum.cryo, rate=self.get_rate1(chara), type_=DMGEnum.charged_atk)
        hit2 = Hit(elem=ELemEnum.cryo, rate=self.get_rate2(chara), type_=DMGEnum.charged_atk)
        print(attr)
        res = f"""
        攻击目标 {self.target.name}
        霜华矢命中(暴击) {get_dmg(chara, attr, hit1, self.target, crit=True)}
        霜华矢绽发(暴击) {get_dmg(chara, attr, hit2, self.target, crit=True)}
        霜华矢命中(暴击融化) {get_dmg(chara, attr, hit1, self.target, melt=True, crit=True)}
        霜华矢绽发(暴击融化) {get_dmg(chara, attr, hit2, self.target, melt=True, crit=True)}
        """.strip()
        return res

    def get_rate1(self, chara: Chara):
        rate1 = [1.28, 1.38, 1.47, 1.60, 1.70, 1.79, 1.92, 2.05, 2.18, 2.30, 2.43]
        return rate1[chara.hit_level - 1]
    
    def get_rate2(self, chara: Chara):
        rate2 = [2.18, 2.34, 2.50, 2.72, 2.88, 3.05, 3.26, 3.48, 3.70, 3.92, 4.13]
        return rate2[chara.hit_level - 1]

@add_calculator
class Leidian(BaseDMGCalculator):
    chara_name = '雷电将军'
    keyword: str = '奶香刀'
    remarks = '仅计算满愿力拔刀伤害'

    def get_result(self, chara: Chara):
        attr: Attr = get_total_attr(chara)
        if chara.level > 60:
            attr.eletro += (attr.energy_recharge - 1) * 0.4 # 固有天赋1
        if chara.rank >= 2:
            attr.DEF_bonus += 0.6

        e = [0.22, 0.23, 0.24, 0.25, 0.26, 0.27, 0.28, 0.29, 0.30, 0.30, 0.30, 0.30, 0.30]
        print('e给的大招加成', e[chara.elem_skill_level-1] * 90 / 100)
        attr.elem_burst_bonus += e[chara.elem_skill_level-1] * 90 / 100 # e技能大招加成

        hit1 = Hit(elem=ELemEnum.eletro, rate=self.get_rate(chara, 60), type_=DMGEnum.elem_burst)
        hit2 = Hit(elem=ELemEnum.eletro, rate=self.get_rate(chara, 0), type_=DMGEnum.elem_burst)
        print('倍率是', self.get_rate(chara, 60))
        print(attr)
        res = f"""
        攻击目标 {self.target.name}
        0愿力拔刀(暴击) {get_dmg(chara, attr, hit2, self.target, crit=True)}
        满愿力拔刀(暴击) {get_dmg(chara, attr, hit1, self.target, crit=True)}
        """.strip()
        return res

    def get_rate(self, chara: Chara, wish):
        rate1 = [4.01, 4.31, 4.61, 5.01, 5.31, 5.61, 6.01, 6.41, 6.81, 7.21, 7.62, 8.02, 8.52]
        wish_b = [3.89, 4.18, 4.47, 4.86, 5.15, 5.44, 5.83, 6.22, 6.61, 7.00, 7.39, 7.78, 8.26]
        return rate1[chara.elem_burst_level - 1] + wish_b[chara.elem_burst_level - 1] * wish / 100

        

    


