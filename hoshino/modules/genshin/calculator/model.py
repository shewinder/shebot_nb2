from typing import Dict
from pathlib import Path
from math import floor

from pydantic import BaseModel

from hoshino.util.sutil import load_config
from .weapon_basic import WEAPON_BASIC_FAMILY, WEAPON_SEC_TAG
from .chara_basic import CHARA_SECOND_TAG
from .const import ENTS
from hoshino.util.sutil import save_config, load_config
from .enums import *

class Attr(BaseModel):
    ATK: int = 0 # 小攻击
    ATK_bonus: float = 0
    HP: float = 0
    HP_bonus: float = 0
    crit_rate: float = 0
    crit_dmg: float = 0
    DEF: int = 0
    DEF_bonus: float = 0
    energy_recharge: float = 0
    pyro: float = 0 # 火伤加成
    hydro: float = 0 # 水伤加成
    dendro: float = 0 # 岩伤加成
    eletro: float = 0 # 雷伤加成
    anemo: float = 0 # 风伤加成
    cryo: float = 0 # 冰伤加成
    physical: float = 0 # 物伤加成
    elem_mastery: float = 0 # 元素精通
    vaporize_bonus: float = 0 # 蒸发系数加成
    melt_bonus: float = 0 # 融化系数加成
    elem_skill_bonus: float = 0 # 元素战技加成
    elem_burst_bonus: float = 0 # 元素爆发加成
    hit_bonus: float = 0 #普攻加成
    charged_hit_bonus: float = 0 # 重击加成
    plunge_hit_bonus: float = 0 # 下落攻击加成
    DEF_decrease: float = 0 # 减少防御
    healing_bonus: float = 0 # 治疗加成

    class Config:
        extra = 'forbid'

    def __add__(self, other):
        for k in self.dict():
            if isinstance(self.__dict__[k], int) or isinstance(self.__dict__[k], float):
                self.__dict__[k] += other.__dict__[k]
        return self


class Weapon(BaseModel):
    type_: str = WeaponTypeEnum.DEFAULT
    name: str
    level: int
    second_tag: str # 副词条
    baseATK: int
    refinement: int = 1 #武器精炼等级
    attr: Attr = Attr()

    @classmethod
    def create(cls, name, refinement, level):
        weapon_data = load_config(Path(__file__).parent.joinpath('weapon_data.json'))
        weapon_data: Dict = weapon_data.get(name)
        if not weapon_data:
            raise ValueError('不存在此武器')
        type_ = weapon_data.get('type')
        atk_list = WEAPON_BASIC_FAMILY[weapon_data.get('basic_family')]
        atk = cls.get_basic_atk(atk_list, level)
        print(weapon_data)
        second_tag = weapon_data.get('second_tag')
        print(second_tag)
        second_family = weapon_data.get('second_family')
        second_list = WEAPON_SEC_TAG.get(second_tag)[second_family]
        attr = Attr()
        attr.__dict__[second_tag] += cls.get_second_tag(second_list, level)
        w = cls(type_=type_, name=name, level=level, second_tag=second_tag, baseATK=atk, refinement=refinement, attr=attr)
        return w
    
    def get_basic_atk(seq, level):
        """
        计算武器基础攻击力，不考虑突破即80级代表80未突破
        """
        if level < 1 or level > 90:
            raise ValueError('武器等级超出范围') 
        if level == 1:
            return seq[0]
        temp = [1, 20, 40, 50, 60, 70, 80, 90]
        index = 0
        while (index < len(temp) and temp[index] < level):
            index += 1
        lowerValue = seq[(index - 1) * 2]
        upperValue = seq[index * 2 - 1]
        return (upperValue - lowerValue) / (temp[index] - temp[index - 1]) * (level - temp[index - 1]) + lowerValue

    def get_second_tag(seq, level):
        """
        计算武器副词条加成
        """
        if level == 1:
            return seq[0]
        
        temp = [1, 20, 40, 50, 60, 70, 80, 90]
        index = 0
        while (index < len(temp) and temp[index] < level):
            index += 1
        if level == temp[index]:
            return seq[index]
        range = seq[index] - seq[index - 1]
        delta = range / (temp[index] - temp[index - 1])
        count = floor(level / 5) - floor(temp[index - 1] / 5)
        return seq[index - 1] + delta * count * 5
 



class Artifact(BaseModel):
    attr: Attr = Attr()
    type_: str = None #圣遗物套装名称
    ch: str = ArtCHEnum.DEFAULT
    eng: str = ArtENGEnum.DEFAULT

    def __add__(self, other):
        self.attr + other.attr
        return self

    def __str__(self) -> str:
        ent = {v:k for k,v in ENTS.items()}
        a = [self.ch]
        for k, v in self.attr.dict().items():
            if v != 0:
                a.append(f'{ent.get(k)}: {round(v, 3)}')
        return '\n'.join(a)

class ArtifactSet(BaseModel):
    flower: Artifact = Artifact() #花
    plume: Artifact = Artifact() #羽毛
    sand: Artifact = Artifact() #时之沙
    goblet: Artifact = Artifact() #杯子
    circlet: Artifact = Artifact() #帽子

    def occupied(self, art):
        return self.__dict__.get(art.eng).type_ != None

    def add(self, art: Artifact):
            self.__dict__[art.eng] = art

    def replace(self, art: Artifact):
            self.__dict__[art.eng] = art
    
    def count(self):
        cnt = 0
        for k, v in self.__dict__.items():
            if v.type_ != None:
                cnt +=1
        return cnt

    def sum(self):
        return self.flower + self.plume + self.sand + self.goblet + self.circlet
    
    def save_to_file(self, path, name):
        a = load_config(path)
        a[name] = self.dict()
        save_config(a, path)


class Chara(BaseModel):
    name: str
    elem: str
    type_: str
    rank: int
    level: int
    baseATK: int = 0
    baseHP: int = 0
    baseDEF: int = 0
    attr: Attr()
    weapon: Weapon
    art_set = ArtifactSet()
    hit_level: int
    elem_skill_level: int
    elem_burst_level: int


    @classmethod
    def create(cls, name, rank, level, weapon, hit_level, elem_skill_level, elem_burst_level):
        chara_data = load_config(Path(__file__).parent.joinpath('chara_data.json'))
        chara_data: Dict = chara_data.get(name)
        if not chara_data:
            raise ValueError('不存在此角色')
        base_atk = cls.get_basic_value(chara_data.get('attack'), level)
        base_hp = cls.get_basic_value(chara_data.get('hp'), level)
        base_def = cls.get_basic_value(chara_data.get('def'), level)
        print(chara_data)
        second_tag = chara_data.get('second_tag')
        second_family = chara_data.get('second_family')
        elem = chara_data.get('elem')
        type_ = chara_data.get('type_')
        print(second_tag)
        second_list = CHARA_SECOND_TAG.get(second_tag)[second_family]
        attr = Attr()
        attr.__dict__[second_tag] += cls.get_second(second_list, level)
        return cls(
            name = name,
            elem = elem,
            type_ = type_,
            rank = rank,
            level = level,
            baseATK = base_atk,
            baseHP = base_hp,
            baseDEF = base_def,
            attr = Attr(energy_recharge=1.0, crit_rate=0.05, crit_dmg=0.5) + attr,
            weapon = weapon,
            hit_level = hit_level,
            elem_skill_level = elem_skill_level,
            elem_burst_level = elem_burst_level
        )
    
    def save_to_file(self, path):
        a = load_config(path)
        a[self.name] = self.dict()
        save_config(a, path)

        
    def get_basic_value(seq, level):
        """
        计算人物基础值
        """
        if level < 1 or level > 90:
            raise ValueError('角色等级超出范围') 
        if level == 1:
            return seq[0]
        temp = [1, 20, 40, 50, 60, 70, 80, 90]
        index = 0
        while (index < len(temp) and temp[index] < level):
            index += 1
        lowerValue = seq[(index - 1) * 2]
        upperValue = seq[index * 2 - 1]
        return (upperValue - lowerValue) / (temp[index] - temp[index - 1]) * (level - temp[index - 1]) + lowerValue

    def get_second(seq, level):
        if level <= 40:
            return 0
        if level % 10 == 0:
            level -= 1
        index = (level - 40) // 10 + 1
        print(level, index)
        return seq[index]







