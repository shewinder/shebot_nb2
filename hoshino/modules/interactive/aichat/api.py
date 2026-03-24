"""
API 管理模块
管理大模型 API 配置和选择
"""
from typing import Any, Dict, List, Optional
from loguru import logger

from hoshino.config import save_plugin_config
from .config import Config
import httpx

# 加载配置
conf = Config.get_instance('aichat')

async def fetch_available_models(api_base: str, api_key: str) -> List[str]:
    """从 API 厂商获取可用模型列表
    
    尝试访问 OpenAI 格式的 /v1/models 端点
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    
    # 尝试可能的端点
    base = api_base.rstrip('/')
    urls_to_try = [
        f"{base}/v1/models",
        f"{base}/models",
    ]
    
    for url in urls_to_try:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("data", [])
                    # 提取模型 ID，过滤空值
                    model_ids = []
                    for m in models:
                        model_id = m.get("id") or m.get("name") or m.get("model", "")
                        if model_id:
                            model_ids.append(model_id)
                    return model_ids
        except httpx.TimeoutException:
            logger.warning(f"获取模型列表超时: {url}")
            continue
        except Exception as e:
            logger.debug(f"获取模型列表失败 {url}: {e}")
            continue
    
    return []


def _build_api_config_dict(api_entry) -> Dict[str, Any]:
    """从 ApiEntry 构建完整 API 调用参数字典"""
    config_dict = {
        "api_base": api_entry.api_base,
        "api_key": api_entry.api_key,
        "model": api_entry.model,
        "supports_multimodal": api_entry.supports_multimodal if api_entry.supports_multimodal is not None else False,
        "supports_tools": api_entry.supports_tools if api_entry.supports_tools is not None else False,
    }
    # 仅当值不为 None 时才添加到配置，让 API 使用模型默认值
    if api_entry.max_tokens is not None:
        config_dict["max_tokens"] = api_entry.max_tokens
    if api_entry.temperature is not None:
        config_dict["temperature"] = api_entry.temperature
    return config_dict


class ApiManager:
    """管理当前使用的大模型 API（全局唯一）"""
    
    def get_current_api(self) -> str:
        """获取当前厂商"""
        return conf.get_current_api()
    
    def set_current_api(self, api: str) -> bool:
        """切换厂商"""
        if not conf.set_current_api(api):
            return False
        save_plugin_config("aichat", conf)
        return True
    
    def get_current_model(self) -> str:
        """获取当前厂商使用的模型"""
        api = self.get_current_api()
        entry = conf.get_api_by_name(api)
        return entry.model if entry else ""
    
    def set_current_model(self, model: str) -> bool:
        """修改当前厂商的模型"""
        api = self.get_current_api()
        entry = conf.get_api_by_name(api)
        if not entry:
            return False
        entry.model = model
        save_plugin_config("aichat", conf)
        return True
    
    def get_api_config(self) -> Optional[Dict[str, Any]]:
        """获取当前应使用的 API 配置"""
        api = self.get_current_api()
        entry = conf.get_api_by_name(api)
        if not entry:
            return None
        return _build_api_config_dict(entry)
    
    async def get_available_models(self) -> List[str]:
        """获取当前 API 支持的所有模型"""
        config = self.get_api_config()
        if not config:
            return []
        return await fetch_available_models(config["api_base"], config["api_key"])


# 全局 API 管理器
api_manager = ApiManager()
