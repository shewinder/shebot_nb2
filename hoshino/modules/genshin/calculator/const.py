from .enums import ELemEnum

#百分比词条
ENTS_PER = {
    '生命值': 'HP_bonus',
    '防御力': 'DEF_bonus',
    '攻击力': 'ATK_bonus',
    '火元素伤害加成': ELemEnum.pyro,
    '水元素伤害加成': ELemEnum.hydro,
    '冰元素伤害加成': ELemEnum.cryo,
    '风元素伤害加成': ELemEnum.anemo,
    '雷元素伤害加成': ELemEnum.eletro,
    '岩元素伤害加成': ELemEnum.dendro,
    '物理伤害加成': ELemEnum.physical,
    '元素充能效率': 'energy_recharge',
    '暴击率': 'crit_rate',
    '暴击伤害': 'crit_dmg'
}

# 固定词条
ENTS_FIX = {
    '生命值': 'HP',
    '防御力': 'DEF',
    '元素精通': 'elem_mastery',
    '攻击力': 'ATK',
}

# 展示用
ENTS = {
    '生命值': 'HP',
    '防御力': 'DEF',
    '元素精通': 'elem_mastery',
    '攻击力': 'ATK',
    '生命值加成': 'HP_bonus',
    '防御力加成': 'DEF_bonus',
    '攻击力加成': 'ATK_bonus',
    '火元素伤害加成': ELemEnum.pyro,
    '水元素伤害加成': ELemEnum.hydro,
    '冰元素伤害加成': ELemEnum.cryo,
    '风元素伤害加成': ELemEnum.anemo,
    '雷元素伤害加成': ELemEnum.eletro,
    '岩元素伤害加成': ELemEnum.dendro,
    '物理伤害加成': ELemEnum.physical,
    '元素充能效率': 'energy_recharge',
    '暴击率': 'crit_rate',
    '暴击伤害': 'crit_dmg'
}