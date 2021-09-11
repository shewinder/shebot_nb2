from enum import Enum

class ELemEnum(str, Enum):
    pyro = 'pyro'
    hydro = 'hydro'
    dendro = 'dendro'
    eletro = 'eletro'
    anemo = 'anemo'
    cryo = 'cryo'
    physical = 'physical'

class WeaponTypeEnum(str, Enum):
    sword = 'sword'
    sword2 = 'sword2'
    bow = 'bow'
    spear = 'spear'
    book = 'book'
    DEFAULT = 'default'

class ArtCHEnum(str, Enum):
    flower = '生之花'
    plume = '死之羽'
    sand = '时之沙'
    goblet = '空之杯'
    circlet = '理之冠'
    DEFAULT = 'default'

class ArtENGEnum(str, Enum):
    flower = 'flower'
    plume = 'plume'
    sand = 'sand'
    goblet = 'goblet'
    circlet = 'circlet'
    DEFAULT = 'default'

class DMGEnum(int, Enum):
    hit = 0
    charged_atk = 1
    plunge = 3
    elem_skill = 4
    elem_burst = 5