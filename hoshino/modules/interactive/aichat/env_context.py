"""环境上下文构建模块

提供从 Event 构建环境信息的功能，用于注入到 AI 系统提示中。
"""
from typing import Dict, List, Optional, Tuple

from hoshino import Event


# 可扩展的环境信息字段配置
# key: (获取函数, XML属性名, 是否仅在群聊有效)
ENV_CONTEXT_PROVIDERS: Dict[str, tuple] = {
    "user_id": (lambda e: e.user_id, "user_id", False),
    "group_id": (lambda e: getattr(e, 'group_id', None), "group_id", True),
    # 扩展示例：
    # "user_role": (lambda e: get_user_role(e), "role", False),
    # "group_name": (lambda e: get_group_name(e), "group_name", True),
}


def build_static_env_info(event: Event, fields: Optional[List[str]] = None) -> str:
    """构建静态环境信息（XML格式）
    
    Args:
        event: 消息事件
        fields: 要包含的字段列表，None 则使用默认（user_id, group_id）
    
    返回 XML 格式字符串，便于模型理解结构化数据。
    扩展方式：向 ENV_CONTEXT_PROVIDERS 添加字段配置
    """
    if fields is None:
        fields = ["user_id", "group_id"]
    
    attrs = []
    for field in fields:
        if field not in ENV_CONTEXT_PROVIDERS:
            continue
        
        getter, attr_name, group_only = ENV_CONTEXT_PROVIDERS[field]
        try:
            value = getter(event)
        except Exception:
            continue
        
        if value is None:
            continue
        
        # 群聊特有字段，在私聊中跳过
        if group_only and not getattr(event, 'group_id', None):
            continue
        
        # 注意：XML 属性值如果包含特殊字符需要转义
        # 但 user_id/group_id 通常是数字，不需要转义
        # 如果后续添加字符串字段，需要在这里处理转义
        attrs.append(f'{attr_name}="{value}"')
    
    if not attrs:
        return ""
    
    return f'<context type="environment" {" ".join(attrs)} />'
