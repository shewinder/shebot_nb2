from hoshino.config import BaseConfig, configuration

@configuration('aichat')
class Config(BaseConfig):
    """AI Chat插件配置"""
    # API配置
    api_base: str = "https://api.deepseek.com"  # API基础URL
    api_key: str = ""  # API密钥
    model: str = "deepseek-chat"  # 使用的模型
    
    # Session配置
    max_history: int = 100  # 每个session保存的最大历史消息数
    session_timeout: int = 3600  # Session超时时间（秒），0表示永不过期
    
    # 其他配置
    max_tokens: int = 8192  # 最大生成token数
    temperature: float = 0.7  # 温度参数
    
    # 人格配置
    default_persona: str = ""  # 全局默认人格文本
    max_saved_personas: int = 5  # 每个用户最多保存的人格数量