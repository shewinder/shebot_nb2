from typing import Dict, List, Optional
from pydantic import BaseModel

from hoshino.config import BaseConfig, configuration


class MCPServerConfig(BaseModel):
    """MCP Server 配置"""
    id: str                           # 唯一标识
    name: str                         # 显示名称
    transport: str = "stdio"          # stdio | sse | http
    command: Optional[str] = None     # stdio 模式：可执行文件路径
    args: List[str] = []              # stdio 模式：参数
    url: Optional[str] = None         # sse/http 模式：URL
    env: Dict[str, str] = {}          # 环境变量
    headers: Dict[str, str] = {}      # HTTP 请求头，用于鉴权（如 Authorization）
    enabled: bool = True              # 是否启用
    
    # === 渐进式加载相关配置 ===
    description: str = ""             # server 功能描述（用于 AI 选择）
    auto_trigger: bool = True         # 是否允许 AI 自动激活
    keywords: List[str] = []          # 触发关键词列表（可选，用于匹配用户意图）


class ApiEntry(BaseModel):
    """单个厂商配置"""
    api: str = ""              # 厂商唯一标识（如 "kimi", "deepseek"）
    api_base: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-chat"
    supports_multimodal: Optional[bool] = None
    supports_tools: Optional[bool] = True
    max_tokens: Optional[int] = None  # None 表示不传给 API，使用模型默认值
    temperature: Optional[float] = None  # None 表示不传给 API，使用模型默认值


@configuration('aichat')
class Config(BaseConfig):
    """AI Chat插件配置"""
    # 厂商列表
    apis: List[ApiEntry] = [
        ApiEntry(
            api="deepseek",
            api_base="https://api.deepseek.com",
            api_key="your-api-key-here",
            model="deepseek-chat",
        )
    ]

    # 当前选择
    current_api: str = ""  # 当前厂商（空或无效则使用 apis[0]）

    # Session 配置
    max_history: int = 100
    session_timeout: int = 3600  # 秒，0 表示永不过期

    # 记忆系统配置
    enable_memory: bool = True              # 记忆系统总开关
    memory_max_summaries: int = 5           # 保留的最近会话摘要数量
    memory_max_facts: int = 30              # 保留的用户事实数量

    # 人格配置
    default_persona: str = ""

    # Markdown 渲染配置
    enable_markdown_render: bool = False
    markdown_min_length: int = 100

    # MCP 配置
    enable_mcp: bool = True            # MCP 总开关
    mcp_servers: List[MCPServerConfig] = [     # MCP server 列表
        MCPServerConfig(
            id="playwright",
            name="Playwright 浏览器自动化",
            transport="http",
            url="http://localhost:8931/mcp",
            enabled=True
        )
    ]

    # 天气工具配置
    gaode_api_key: str = ""  # 高德地图 API Key，用于天气查询 https://lbs.amap.com/

    # 网页搜索工具配置 (阿里云百炼 IQS)
    # 获取方式: https://bailian.console.aliyun.com/
    # 文档: https://help.aliyun.com/zh/document_detail/2883041.html
    iqs_api_key: str = ""  # 阿里云 IQS API Key，用于网页搜索

    # SKILL 系统配置
    enable_skills: bool = True         # SKILL 系统总开关
    # 用户自定义 SKILL 搜索路径（这些路径的 skill 不会被 git 跟踪）
    skill_user_paths: List[str] = ["data/skills"]
    skill_default_tools: List[str] = ["Read", "Bash"]  # SKILL 默认允许的工具
    skill_max_per_session: int = 5     # 单个会话最大激活 SKILL 数量

    # 工具调用配置
    max_tool_rounds: int = 10           # 单次对话最大工具调用轮数

    def get_apis(self) -> List[ApiEntry]:
        """获取厂商列表"""
        return self.apis

    def get_api_by_name(self, api: str) -> Optional[ApiEntry]:
        """根据 api 名称获取配置"""
        for a in self.apis:
            if a.api == api:
                return a
        return None

    def get_current_api(self) -> str:
        """获取当前厂商（无效时返回第一个）"""
        if self.current_api and self.get_api_by_name(self.current_api):
            return self.current_api
        return self.apis[0].api if self.apis else ""

    def set_current_api(self, api: str) -> bool:
        """设置当前厂商"""
        if not self.get_api_by_name(api):
            return False
        self.current_api = api
        return True
