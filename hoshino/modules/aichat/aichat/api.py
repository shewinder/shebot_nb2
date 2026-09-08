"""API 管理模块"""
from typing import Any, Dict, List, Optional
from loguru import logger

from hoshino.config import save_plugin_config
from .config import ApiEndpoint, Config
import httpx

conf = Config.get_instance('aichat')

async def fetch_available_models(api_base: str, api_key: str) -> List[str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    
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
    endpoints = api_entry.endpoints or [
        ApiEndpoint(
            name=api_entry.api,
            api_base=api_entry.api_base,
            api_key=api_entry.api_key,
            model=api_entry.model,
            supports_multimodal=api_entry.supports_multimodal,
            supports_tools=api_entry.supports_tools,
            max_tokens=api_entry.max_tokens,
            temperature=api_entry.temperature,
        )
    ]

    def build_endpoint(endpoint: ApiEndpoint) -> Dict[str, Any]:
        config = {
            "name": endpoint.name,
            "api_base": endpoint.api_base,
            "api_key": endpoint.api_key,
            "model": endpoint.model,
            "supports_multimodal": endpoint.supports_multimodal if endpoint.supports_multimodal is not None else False,
            "supports_tools": endpoint.supports_tools if endpoint.supports_tools is not None else True,
        }
        if endpoint.max_tokens is not None:
            config["max_tokens"] = endpoint.max_tokens
        if endpoint.temperature is not None:
            config["temperature"] = endpoint.temperature
        return config

    primary = build_endpoint(endpoints[0])
    config_dict = {
        **primary,
        "api": api_entry.api,
        "endpoints": [build_endpoint(endpoint) for endpoint in endpoints],
    }
    return config_dict


class ApiManager:
    def get_current_api(self) -> str:
        return conf.get_current_api()
    
    def set_current_api(self, api: str) -> bool:
        if not conf.set_current_api(api):
            return False
        save_plugin_config("aichat", conf)
        return True
    
    def get_current_model(self) -> str:
        api = self.get_current_api()
        entry = conf.get_api_by_name(api)
        if not entry:
            return ""
        return entry.endpoints[0].model if entry.endpoints else entry.model
    
    def set_current_model(self, model: str) -> bool:
        api = self.get_current_api()
        entry = conf.get_api_by_name(api)
        if not entry:
            return False
        if entry.endpoints:
            entry.endpoints[0].model = model
        else:
            entry.model = model
        save_plugin_config("aichat", conf)
        return True
    
    def get_api_config(self) -> Optional[Dict[str, Any]]:
        api = self.get_current_api()
        entry = conf.get_api_by_name(api)
        if not entry:
            return None
        return _build_api_config_dict(entry)
    
    async def get_available_models(self) -> List[str]:
        config = self.get_api_config()
        if not config:
            return []
        return await fetch_available_models(config["api_base"], config["api_key"])


# 全局 API 管理器
api_manager = ApiManager()
