#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-04-17
Description: ComfyUI 工作流加载与处理模块
Github: https://github.com/

约定：
- 工作流 JSON 放在 skill 目录的 reference/ 下
- 文件名 = 模型名 + .json（如 z_image_turbo.json）
- Prompt 占位符: {{prompt}}
- 图片占位符: {{input_image}} / {{input_image_1}} / {{input_image_2}} ...
"""
import json
from pathlib import Path
from typing import Any, Dict, List


# ---------- 配置目录 ----------
CONFIG_DIR = Path(__file__).parent.parent / "reference"

# ---------- 尺寸映射 ----------
_SIZE_MAP: Dict[str, Dict[str, int]] = {
    "": {"width": 1024, "height": 1536},
    "1:1": {"width": 1024, "height": 1024},
    "4:3": {"width": 1280, "height": 960},
    "3:4": {"width": 960, "height": 1280},
    "16:9": {"width": 1536, "height": 864},
    "9:16": {"width": 864, "height": 1536},
    "2:3": {"width": 1024, "height": 1536},
    "3:2": {"width": 1536, "height": 1024},
}

# ---------- Latent 图像节点类型 ----------
_LATENT_IMAGE_CLASSES = {
    "EmptySD3LatentImage",
    "EmptyLatentImage",
    "EmptyLatentImageSDXL",
}

# ---------- LoRA 节点类型 ----------
# class_type -> {输出槽位: 对应的上游输入名}，用于删除节点时把下游改接上游
_LORA_CLASSES: Dict[str, Dict[int, str]] = {
    "LoraLoaderModelOnly": {0: "model"},
    "LoraLoader": {0: "model", 1: "clip"},
}


def list_available_models() -> List[str]:
    """扫描 reference/ 目录，返回所有可用模型名（不含 .json 后缀）"""
    if not CONFIG_DIR.exists():
        return []
    models = [f.stem for f in CONFIG_DIR.glob("*.json")]
    return sorted(models)


def load_workflow(model_name: str) -> Dict[str, Any]:
    """加载指定模型的工作流 JSON

    Args:
        model_name: 模型名称（对应 reference/ 下的 .json 文件名）

    Returns:
        工作流 dict

    Raises:
        RuntimeError: 文件不存在或解析失败
    """
    wf_path = CONFIG_DIR / f"{model_name}.json"
    if not wf_path.exists():
        available = ", ".join(list_available_models())
        raise RuntimeError(f"未找到工作流: {model_name}。可用工作流: {available}")

    try:
        return json.loads(wf_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"加载工作流 {model_name} 失败: {e}")


def _replace_placeholder(obj: Any, placeholder: str, value: str) -> None:
    """递归替换对象中的指定占位符字符串"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v == placeholder:
                obj[k] = value
            else:
                _replace_placeholder(v, placeholder, value)
    elif isinstance(obj, list):
        for item in obj:
            _replace_placeholder(item, placeholder, value)


def apply_prompt(workflow: Dict[str, Any], prompt: str) -> None:
    """替换工作流中的 {{prompt}} 占位符"""
    _replace_placeholder(workflow, "{{prompt}}", prompt)


def apply_input_images(workflow: Dict[str, Any], filenames: List[str]) -> None:
    """替换工作流中的多图占位符

    支持两种占位符风格：
    - {{input_image}}        : 单图兼容，替换为第一张
    - {{input_image_1}}      : 多图，替换为第 1 张
    - {{input_image_2}}      : 多图，替换为第 2 张
    - ... 依此类推
    """
    if not filenames:
        return

    # 单图兼容占位符
    _replace_placeholder(workflow, "{{input_image}}", filenames[0])

    # 多图编号占位符
    for i, name in enumerate(filenames, start=1):
        _replace_placeholder(workflow, "{{input_image_" + str(i) + "}}", name)


def apply_size(workflow: Dict[str, Any], aspect_ratio: str) -> None:
    """根据宽高比调整 Latent 图像节点的尺寸"""
    size = _SIZE_MAP.get(aspect_ratio, _SIZE_MAP[""])
    for node in workflow.values():
        if isinstance(node, dict) and node.get("class_type") in _LATENT_IMAGE_CLASSES:
            inputs: Dict[str, Any] = node.get("inputs", {})
            inputs["width"] = size["width"]
            inputs["height"] = size["height"]
            break


def _is_link(value: Any) -> bool:
    """判断是否为节点连线 [node_id, output_slot]"""
    return (isinstance(value, list) and len(value) == 2
            and isinstance(value[0], str) and isinstance(value[1], int))


def _resolve_upstream(workflow: Dict[str, Any], link: List[Any],
                      lora_ids: set) -> List[Any]:
    """穿透（可能级联的）LoRA 节点，返回真正的上游连线"""
    seen: set = set()
    node_id, slot = link
    while node_id in lora_ids and node_id in workflow and node_id not in seen:
        seen.add(node_id)
        input_key = _LORA_CLASSES[workflow[node_id]["class_type"]].get(slot)
        if not input_key:
            break
        upstream = workflow[node_id].get("inputs", {}).get(input_key)
        if not _is_link(upstream):
            break
        link = upstream
        node_id, slot = link
    return link


def apply_lora_weight(workflow: Dict[str, Any], weight: float) -> List[str]:
    """动态设置工作流中所有 LoRA 节点的强度

    weight > 0 时写入 strength_model；weight <= 0 时删除 LoRA 节点，
    并把下游连线改接到该节点的上游（等效于该工作流不带 LoRA 的版本）。

    Returns:
        受影响的 LoRA 节点 id 列表（工作流无 LoRA 节点时为空）
    """
    lora_ids = [nid for nid, node in workflow.items()
                if isinstance(node, dict) and node.get("class_type") in _LORA_CLASSES]
    if not lora_ids:
        return []

    if weight > 0:
        for nid in lora_ids:
            inputs: Dict[str, Any] = workflow[nid].setdefault("inputs", {})
            inputs["strength_model"] = weight
            if "strength_clip" in inputs:
                inputs["strength_clip"] = weight
        return lora_ids

    lora_id_set = set(lora_ids)
    for nid in lora_ids:
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            for key, value in node.get("inputs", {}).items():
                if _is_link(value) and value[0] == nid:
                    node["inputs"][key] = _resolve_upstream(workflow, value, lora_id_set)
        del workflow[nid]
    return lora_ids
