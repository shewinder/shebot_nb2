#!/usr/bin/env python3
"""
ComfyUI 通用图像生成脚本

支持通过 --model 参数加载不同的内置工作流，便于灵活扩展：
- z_image_turbo: Lumina2 + AuraFlow + qwen CLIP，中文理解强
- 未来可扩展更多模型/工作流（含 LoRA 等）

特点：
- 保留中文提示词（qwen CLIP 模型下）
- 支持自定义工作流参数
- 可通过配置文件扩展新工作流
"""
import copy
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent))
import argparse

from _common import (
    get_image_paths, resolve_image_file,
    store_image, read_image_file, http_post, http_get,
    output_result, output_error
)


# ---------- 工作流注册表 ----------
# 每个工作流是一个完整的 ComfyUI API 格式工作流 JSON
# prompt 中需包含 {{prompt}} 占位符，调用时会被替换
_WORKFLOWS = {
    "z_image_turbo": {
    "9": {
        "inputs": {
            "filename_prefix": "z-image-turbo",
            "images": ["57:8", 0]
        },
        "class_type": "SaveImage",
        "_meta": {"title": "保存图像"}
    },
    "57:30": {
        "inputs": {
            "clip_name": "qwen_3_4b.safetensors",
            "type": "lumina2",
            "device": "default"
        },
        "class_type": "CLIPLoader",
        "_meta": {"title": "加载CLIP"}
    },
    "57:29": {
        "inputs": {"vae_name": "ae.safetensors"},
        "class_type": "VAELoader",
        "_meta": {"title": "加载VAE"}
    },
    "57:33": {
        "inputs": {"conditioning": ["57:27", 0]},
        "class_type": "ConditioningZeroOut",
        "_meta": {"title": "条件零化"}
    },
    "57:8": {
        "inputs": {
            "samples": ["57:3", 0],
            "vae": ["57:29", 0]
        },
        "class_type": "VAEDecode",
        "_meta": {"title": "VAE解码"}
    },
    "57:28": {
        "inputs": {
            "unet_name": "z_image_turbo_bf16.safetensors",
            "weight_dtype": "default"
        },
        "class_type": "UNETLoader",
        "_meta": {"title": "UNet加载器"}
    },
    "57:27": {
        "inputs": {
            "text": "{{prompt}}",
            "clip": ["57:30", 0]
        },
        "class_type": "CLIPTextEncode",
        "_meta": {"title": "CLIP文本编码"}
    },
    "57:13": {
        "inputs": {
            "width": 1024,
            "height": 1536,
            "batch_size": 1
        },
        "class_type": "EmptySD3LatentImage",
        "_meta": {"title": "空Latent图像（SD3）"}
    },
    "57:11": {
        "inputs": {
            "shift": 3,
            "model": ["57:28", 0]
        },
        "class_type": "ModelSamplingAuraFlow",
        "_meta": {"title": "采样算法（AuraFlow）"}
    },
    "57:3": {
        "inputs": {
            "seed": 889694652031182,
            "steps": 8,
            "cfg": 1,
            "sampler_name": "res_multistep",
            "scheduler": "simple",
            "denoise": 1,
            "model": ["57:11", 0],
            "positive": ["57:27", 0],
            "negative": ["57:33", 0],
            "latent_image": ["57:13", 0]
        },
        "class_type": "KSampler",
        "_meta": {"title": "K采样器"}
    }
}
}


def get_workflow(model_name: str) -> dict:
    """获取指定模型的工作流，找不到则返回 z_image_turbo 作为默认"""
    return _WORKFLOWS.get(model_name, _WORKFLOWS["z_image_turbo"])


# ---------- 尺寸映射 ----------
_SIZE_MAP = {
    "": {"width": 1024, "height": 1536},
    "1:1": {"width": 1024, "height": 1024},
    "4:3": {"width": 1280, "height": 960},
    "3:4": {"width": 960, "height": 1280},
    "16:9": {"width": 1536, "height": 864},
    "9:16": {"width": 864, "height": 1536},
    "2:3": {"width": 1024, "height": 1536},
    "3:2": {"width": 1536, "height": 1024},
}


def _replace_prompt(obj, prompt: str) -> None:
    """递归替换工作流中的 {{prompt}} 占位符"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v == "{{prompt}}":
                obj[k] = prompt
            else:
                _replace_prompt(v, prompt)
    elif isinstance(obj, list):
        for item in obj:
            _replace_prompt(item, prompt)


def _apply_size(workflow: dict, aspect_ratio: str) -> None:
    """根据宽高比调整 EmptySD3LatentImage 尺寸"""
    size = _SIZE_MAP.get(aspect_ratio, _SIZE_MAP[""])
    for node in workflow.values():
        if isinstance(node, dict) and node.get("class_type") == "EmptySD3LatentImage":
            node["inputs"]["width"] = size["width"]
            node["inputs"]["height"] = size["height"]
            break


# ComfyUI API 基础地址（环境变量或默认本地地址）
COMFYUI_BASE_URL = os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188")


def call_comfyui_generate(prompt: str,
                          aspect_ratio: str = "", model_name: str = "") -> dict:
    """调用 ComfyUI 生成图片"""
    base = COMFYUI_BASE_URL.rstrip("/")
    model_name = model_name or "z_image_turbo"

    wf = copy.deepcopy(get_workflow(model_name))
    _replace_prompt(wf, prompt)
    _apply_size(wf, aspect_ratio)

    url = f"{base}/prompt"
    payload = {"prompt": wf, "client_id": "image_generation_skill"}

    result = http_post(url, json_data=payload)
    if "error" in result:
        return {"success": False, "error": result["error"]}
    if result.get("status", 0) not in (200,):
        return {"success": False, "error": f"HTTP {result.get('status')}: {result.get('text', '')[:200]}"}

    resp = result.get("json", {})
    prompt_id = resp.get("prompt_id")
    if not prompt_id:
        return {"success": False, "error": f"ComfyUI 未返回 prompt_id: {resp}"}

    # 轮询 /history/{prompt_id}
    history_url = f"{base}/history/{prompt_id}"
    timeout = 180
    interval = 2
    elapsed = 0

    while elapsed < timeout:
        time.sleep(interval)
        elapsed += interval

        hist_result = http_get(history_url)
        if "error" in hist_result:
            continue

        hist = hist_result.get("json", {})
        if not isinstance(hist, dict):
            continue

        entry = hist.get(prompt_id, {})
        outputs = entry.get("outputs", {})

        for node_id, node_output in outputs.items():
            images = node_output.get("images", [])
            for img_info in images:
                filename = img_info.get("filename")
                subfolder = img_info.get("subfolder", "")
                img_type = img_info.get("type", "output")
                if filename:
                    view_url = (
                        f"{base}/view?filename={quote(filename)}"
                        f"&subfolder={quote(subfolder)}&type={quote(img_type)}"
                    )
                    img_resp = http_get(view_url)
                    if img_resp.get("status") == 200:
                        content = img_resp.get("content")
                        if content:
                            return {"success": True, "data": content}
                        return {"success": False, "error": "ComfyUI /view 未返回图片数据"}

    return {"success": False, "error": "ComfyUI 生成超时"}


def _parse_args():
    """ComfyUI 专用参数解析（继承通用参数 + --model）"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True, help="图像描述")
    parser.add_argument("--images", default="", help="待编辑图片标识符，逗号分隔")
    parser.add_argument("--aspect-ratio", default="", help="宽高比")
    parser.add_argument("--size", default="", help="分辨率")
    parser.add_argument("--api", default="", help="指定 API 配置名称")
    parser.add_argument("--model", default="", help="ComfyUI 工作流模型名（如 z_image_turbo）")
    return parser.parse_args()


def main():
    args = _parse_args()

    # ComfyUI 当前不支持编辑（工作流未配置编辑模式）
    if args.images:
        output_error("ComfyUI 当前不支持图像编辑，请使用 gemini.py 或 openai.py")
        return

    result = call_comfyui_generate(args.prompt, aspect_ratio=args.aspect_ratio, model_name=args.model)

    if not result.get("success"):
        output_error(result.get("error", "未知错误"))
        return

    img_data = result.get("data")
    if not img_data:
        output_error("ComfyUI 未返回图片数据")
        return

    stored = store_image(img_data, "ai", "png")
    output_result(
        True,
        identifier=stored["identifier"],
        path=stored["path"],
        model=args.model or "z_image_turbo",
    )


if __name__ == "__main__":
    main()
