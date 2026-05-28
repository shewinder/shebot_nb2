from typing import List
from hoshino.config import BaseConfig, configuration


@configuration('groupmsglog')
class Config(BaseConfig):
    """群聊消息记录插件配置"""

    # 消息保留天数，0=永久保留
    retention_days: int = 30

    # 单群最大消息数，0=不限制（超出后删除旧消息）
    max_messages_per_group: int = 0

    # 是否记录机器人自己的消息
    record_self_message: bool = False

    # 消息类型过滤，空=不过滤，如 ["text", "image"]
    filter_message_types: List[str] = []
