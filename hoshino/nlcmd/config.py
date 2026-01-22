from pydantic import BaseModel


class Config(BaseModel):
    """自然语言命令触发插件配置"""
    # API配置
    nlcmd_api_base: str = "https://api.deepseek.com"  # API基础URL
    nlcmd_api_key: str = ""  # API密钥
    nlcmd_model: str = "deepseek-chat"  # 使用的模型
    
    # 其他配置
    nlcmd_max_tokens: int = 500  # 最大生成token数
    nlcmd_temperature: float = 0.3  # 温度参数（较低以获得更稳定的输出）
    nlcmd_min_confidence: float = 0.7  # 最小置信度阈值

    @property
    def api_base(self):
        return self.nlcmd_api_base

    @property
    def api_key(self):
        return self.nlcmd_api_key

    @property
    def model(self):
        return self.nlcmd_model

    @property
    def max_tokens(self):
        return self.nlcmd_max_tokens

    @property
    def temperature(self):
        return self.nlcmd_temperature

    @property
    def min_confidence(self):
        return self.nlcmd_min_confidence