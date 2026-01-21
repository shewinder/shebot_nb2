from hoshino.config import BaseConfig, configuration

@configuration('nlcmd')
class Config(BaseConfig):
    """自然语言命令触发插件配置"""
    # API配置
    api_base: str = "https://api.deepseek.com"  # API基础URL
    api_key: str = ""  # API密钥
    model: str = "deepseek-chat"  # 使用的模型
    
    # 其他配置
    max_tokens: int = 500  # 最大生成token数
    temperature: float = 0.3  # 温度参数（较低以获得更稳定的输出）
    min_confidence: float = 0.7  # 最小置信度阈值
