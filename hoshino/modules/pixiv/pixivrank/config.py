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
