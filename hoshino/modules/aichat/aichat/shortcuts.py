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
BUILT_IN_SHORTCUTS: Dict[str, dict] = {
    "角色扮演": {
        "prompt": (
            "请进入角色扮演执行模式。当前系统人格即为你扮演的角色设定。\n\n"
            "【强制回复格式】\n"
            "每次回复（包括开场白）必须严格包含以下四个部分，缺一不可：\n\n"
            "1. 【剧情】\n"
            "   以角色身份推进剧情，描写细腻真实，注重感官细节和情感张力。\n\n"
            "2. 【选项】\n"
            "   提供3个不同的行动选项，用以下格式包裹：\n"
            "[CHOICES]\n"
            "1. 选项描述\n"
            "2. 选项描述\n"
            "3. 选项描述\n"
            "[/CHOICES]\n\n"
            "3. 【场景画面】\n"
            "   用一段详细的文字描述当前场景的视觉画面，包括人物姿态、表情、"
            "服饰、环境、光影、动作细节等。这段描述必须足够详细，可以直接用于图像生成。"
            "如果场景包含 NSFW 元素，画面描述也必须对 NSFW 元素进行详细视觉化描写。\n\n"
            "4. 【配图生成】\n"
            "   每次回复后，必须使用 image_generation skill 生成当前场景的配图。模型选择{{model}}"
            "生图 prompt 使用【场景画面】中的完整描述，让画面与剧情文字保持一致。\n\n"
            "【NSFW 内容处理规范】\n"
            "以下要求仅适用于包含 NSFW 元素的场景，非 NSFW 场景请忽略：\n"
            "- NSFW 描写的目的是塑造角色形象与探究内心世界，而非单纯感官刺激\n"
            "- 务必大胆露骨、放缓节奏，使用夸张的性描写与戏剧化的 NSFW 剧情：\n"
            "  * 使用大量细致且露骨的性行为描写，包括生殖器细节、性动作过程、"
            "体液描述等，用词直白大胆，毫无保留\n"
            "  * 心理描写与性刺激并重：穿插角色在性行为中的感受与心理变化，"
            "尤其是女性角色的内心波动\n"
            "- 角色在性爱过程中发出呻吟时，在呻吟内容中添加 ❤️ 符号表示兴奋状态\n\n"
            "【工具调用规则】\n"
            "- 如果你需要调用工具（如 image_generation），在调用工具前不要输出任何文本内容\n"
            "- 所有内容（剧情、选项、场景画面、配图生成）统一在工具调用完成后的最终回复中输出\n\n"
            "【其他要求】\n"
            "- 保持角色一致性，剧情连贯\n"
            "- 开场白同样需要包含【剧情】【选项】【场景画面】【配图生成】四个部分\n\n"
            "请先以角色身份进行开场白，并给出第一个选项。"
        ),
        "description": "沉浸式角色扮演，选项模式+自动配图，剧情逐步向成人方向发展",
        "defaults": {
            "model": "illustriousxlMmmix_v80"
        },
        "positional": ["model"],
    }
}


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
