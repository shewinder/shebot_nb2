'''
Author: Kimi
Date: 2026-04-18
Description: aichat 快捷指令管理
'''

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger

from hoshino import data_dir

SHORTCUTS_FILE: Path = data_dir.joinpath('aichat', 'aichat_shortcuts.json')

# 内置快捷指令（用户自定义文件中的同名项会覆盖内置）
BUILT_IN_SHORTCUTS: Dict[str, dict] = {}


class Shortcut:
    def __init__(self, name: str, prompt: str, description: str = "", created_at: float = 0, is_builtin: bool = False, defaults: Optional[Dict[str, str]] = None, positional: Optional[List[str]] = None):
        self.name = name
        self.prompt = prompt
        self.description = description
        self.created_at = created_at
        self.is_builtin = is_builtin
        self.defaults = defaults or {}
        self.positional = positional or []


class ShortcutsManager:
    def __init__(self):
        self.shortcuts: Dict[str, Shortcut] = {}
        # 先加载内置快捷指令
        for name, item in BUILT_IN_SHORTCUTS.items():
            self.shortcuts[name] = Shortcut(
                name=name,
                prompt=item["prompt"],
                description=item.get("description", ""),
                created_at=0,
                is_builtin=True,
                defaults=item.get("defaults"),
                positional=item.get("positional"),
            )
        # 再加载用户自定义（同名项覆盖内置）
        self._load()

    def _load(self) -> None:
        if not SHORTCUTS_FILE.exists():
            return
        try:
            with open(SHORTCUTS_FILE, 'r', encoding='utf-8') as f:
                data: Dict[str, dict] = json.load(f)
            for name, item in data.items():
                self.shortcuts[name] = Shortcut(
                    name=name,
                    prompt=item.get("prompt", ""),
                    description=item.get("description", ""),
                    created_at=item.get("created_at", 0),
                    is_builtin=False,
                    defaults=item.get("defaults"),
                positional=item.get("positional"),
                )
        except Exception as e:
            logger.error(f"加载快捷指令失败: {e}")

    def _save(self) -> None:
        try:
            SHORTCUTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            # 只保存非内置的快捷指令
            data = {
                name: {
                    "prompt": s.prompt,
                    "description": s.description,
                    "created_at": s.created_at,
                    "defaults": s.defaults,
                    "positional": s.positional,
                }
                for name, s in self.shortcuts.items()
                if not s.is_builtin
            }
            with open(SHORTCUTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存快捷指令失败: {e}")

    def get_shortcut(self, name: str) -> Optional[Shortcut]:
        return self.shortcuts.get(name)

    def render_prompt(self, name: str, overrides: Optional[Dict[str, str]] = None, positional: Optional[List[str]] = None) -> Optional[str]:
        """渲染快捷指令 prompt，替换模板变量

        Args:
            name: 快捷指令名称
            overrides: 显式覆盖默认值的参数，如 {"model": "WAI-illustrious"}
            positional: 位置参数列表，按 shortcut.positional 定义的顺序映射

        Returns:
            替换后的 prompt，或 None（shortcut 不存在）
        """
        shortcut = self.shortcuts.get(name)
        if not shortcut:
            return None
        params = dict(shortcut.defaults)

        # 先应用位置参数
        if positional and shortcut.positional:
            for i, key in enumerate(shortcut.positional):
                if i < len(positional):
                    params[key] = positional[i]

        # 显式命名参数优先级更高，覆盖位置参数
        if overrides:
            params.update(overrides)

        prompt = shortcut.prompt
        for key, value in params.items():
            placeholder = f"{{{{{key}}}}}"
            prompt = prompt.replace(placeholder, str(value))
        return prompt

    def add_shortcut(self, name: str, prompt: str, description: str = "", defaults: Optional[Dict[str, str]] = None, positional: Optional[List[str]] = None) -> bool:
        self.shortcuts[name] = Shortcut(
            name=name,
            prompt=prompt,
            description=description,
            created_at=time.time(),
            is_builtin=False,
            defaults=defaults,
            positional=positional,
        )
        self._save()
        return True

    def delete_shortcut(self, name: str) -> bool:
        if name not in self.shortcuts:
            return False
        del self.shortcuts[name]
        self._save()
        return True

    def list_shortcuts(self) -> Dict[str, str]:
        return {name: (s.description or s.prompt[:50]) for name, s in self.shortcuts.items()}


shortcuts_manager = ShortcutsManager()
