from hoshino.config import BaseConfig, configuration

@configuration('pixivrank')
class Config(BaseConfig):
    hour: int = 18  # after 18:00 to ensure the rank is up-to-date
    minute: int = 30  # less than 55 because r18 rank is  minutes later
    
    # AI 筛选配置（独立配置，可与 aichat 使用不同模型）
    ai_filter_enabled: bool = True  # AI 筛选总开关
    ai_api_base: str = "https://api.deepseek.com"
    ai_api_key: str = ""
    ai_model: str = "deepseek-chat"
    ai_select_count: int = 15  # AI 筛选返回数量

    # Vision 视觉筛选配置（看图筛选，独立于文本 AI）
    vision_filter_enabled: bool = True  # 视觉筛选总开关，关闭时回退纯文本
    vision_api_base: str = ""
    vision_api_key: str = ""
    vision_model: str = "grok-4.3"
    vision_batch_size: int = 10  # 每批传给 vision 模型的图片数
    vision_select_per_user: int = 4  # 每批每用户最多选几张
