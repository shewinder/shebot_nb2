"""
API 管理模块
管理大模型 API 配置和选择
"""
import json
from typing import Any, Dict, Optional
from pathlib import Path
from loguru import logger

from hoshino import userdata_dir
from .config import Config

# 加载配置
conf = Config.get_instance('aichat')

# 运行时数据目录（data/aichat）
aichat_data_dir: Path = userdata_dir.joinpath('aichat')


def _build_api_config_dict(api_entry) -> Dict[str, Any]:
    """从 ApiEntry 构建完整 API 调用参数字典（只包含配置的参数）"""
    config_dict = {
        "api_base": api_entry.api_base,
        "api_key": api_entry.api_key,
        "model": api_entry.model,
    }
    # 只在配置了参数时才添加（不强制使用默认值）
    if api_entry.max_tokens is not None:
        config_dict["max_tokens"] = api_entry.max_tokens
    if api_entry.temperature is not None:
        config_dict["temperature"] = api_entry.temperature
    # 多模态支持标志（None 表示未配置，默认为 False）
    config_dict["supports_multimodal"] = api_entry.supports_multimodal if api_entry.supports_multimodal is not None else False
    # Tool/Function Calling 支持标志（None 表示未配置，默认为 False）
    config_dict["supports_tools"] = api_entry.supports_tools if api_entry.supports_tools is not None else False
    return config_dict


class ApiManager:
    """管理当前使用的大模型 API（全局唯一）"""
    def __init__(self):
        self._current_api_id: str = ""
        self.data_file = aichat_data_dir.joinpath('aichat_api_selection.json')
        self.load()

    def load(self):
        try:
            if self.data_file.exists():
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # 新格式：{"current_api": "kimi"}；旧格式（按用户）取第一个有效值或忽略
                if isinstance(data, dict) and "current_api" in data:
                    self._current_api_id = data.get("current_api", "") or ""
                else:
                    self._current_api_id = ""
        except Exception as e:
            logger.error(f"加载 API 选择失败: {e}")
            self._current_api_id = ""

    def save(self):
        try:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump({"current_api": self._current_api_id}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存 API 选择失败: {e}")

    def get_current_api_id(self) -> str:
        """获取当前全局使用的 API id"""
        if self._current_api_id and conf.get_api_by_id(self._current_api_id):
            return self._current_api_id
        return conf.get_default_api_id()

    def set_current_api_id(self, api_id: str) -> bool:
        """设置全局当前使用的 API id（仅超级用户应调用）"""
        if not conf.get_api_by_id(api_id):
            return False
        self._current_api_id = api_id
        self.save()
        return True

    def get_api_config(self) -> Optional[Dict[str, Any]]:
        """获取当前应使用的 API 配置（完整 dict）"""
        api_id = self.get_current_api_id()
        entry = conf.get_api_by_id(api_id)
        if not entry:
            return None
        return _build_api_config_dict(entry)


# 全局 API 管理器
api_manager = ApiManager()
