#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-04-17
Description: ComfyUI 通用图像生成脚本
Github: https://github.com/

约定：
- 工作流 JSON 放在 skill 目录的 reference/ 下，文件名 = 模型名 + .json
- Prompt 占位符: {{prompt}}
- 图片占位符: {{input_image}} / {{input_image_1}} / {{input_image_2}} ...
- 能力判断交给 AI，脚本不做拦截，ComfyUI 报错直接透传
"""
import copy
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent))
import argparse

from _common import (
    get_image_paths, resolve_image_file,
    store_image, read_image_file, http_post, http_get,
    output_result, output_error
)
from comfyui_workflow_loader import (
    load_workflow,
    apply_prompt, apply_input_images, apply_size,
    list_available_models,
)


COMFYUI_BASE_URL = os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188")


def upload_image_to_comfyui(image_path: str) -> str:
    """上传本地图片到 ComfyUI 服务器，返回文件名"""
    base = COMFYUI_BASE_URL.rstrip("/")
    url = f"{base}/upload/image"

    data = read_image_file(image_path)
    files = {"image": (Path(image_path).name, data, "image/png")}

    result = http_post(url, files=files)
    if "error" in result:
        raise RuntimeError(f"上传图片到 ComfyUI 失败: {result['error']}")
    if result.get("status", 0) not in (200,):
        raise RuntimeError(
            f"ComfyUI 上传图片失败 HTTP {result.get('status')}: "
            f"{result.get('text', '')[:200]}"
        )

    resp = result.get("json", {})
    if not isinstance(resp, dict):
        raise RuntimeError(f"ComfyUI 上传返回格式异常: {resp}")

    filename = resp.get("name")
    if not filename:
        raise RuntimeError(f"ComfyUI 上传未返回文件名: {resp}")
    return filename


def call_comfyui_generate(prompt: str,
                          aspect_ratio: str = "",
                          model_name: str = "",
                          image_paths: Optional[List[str]] = None) -> Dict[str, Any]:
    """调用 ComfyUI 生成图片

    Args:
        prompt: 图像描述
        aspect_ratio: 宽高比
        model_name: 工作流模型名（对应 reference/ 下的 .json 文件名）
        image_paths: 本地图片路径列表

    Returns:
        {"success": True, "data": bytes} 或 {"success": False, "error": str}
    """
    base = COMFYUI_BASE_URL.rstrip("/")
    if not model_name:
        return {"success": False, "error": "--model 参数必填"}

    wf = copy.deepcopy(load_workflow(model_name))

    # 替换 prompt
    apply_prompt(wf, prompt)

    # 处理图片上传并替换占位符
    if image_paths:
        uploaded_names: List[str] = []
        for image_path in image_paths:
            try:
                uploaded_name = upload_image_to_comfyui(image_path)
                uploaded_names.append(uploaded_name)
            except Exception as e:
                return {"success": False, "error": f"图片上传失败 ({image_path}): {e}"}
        apply_input_images(wf, uploaded_names)

    # 调整尺寸
    apply_size(wf, aspect_ratio)

    # 提交任务
    url = f"{base}/prompt"
    payload = {"prompt": wf, "client_id": "image_generation_skill"}

    result = http_post(url, json_data=payload)
    if "error" in result:
        return {"success": False, "error": result["error"]}
    if result.get("status", 0) not in (200,):
        return {
            "success": False,
            "error": f"HTTP {result.get('status')}: {result.get('text', '')[:200]}"
        }

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


def _parse_args() -> argparse.Namespace:
    """参数解析"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True, help="图像描述")
    parser.add_argument("--images", default="", help="待编辑图片标识符，逗号分隔")
    parser.add_argument("--aspect-ratio", default="", help="宽高比")
    parser.add_argument("--size", default="", help="分辨率")
    parser.add_argument("--api", default="", help="指定 API 配置名称")
    parser.add_argument("--model", default="", help="ComfyUI 工作流模型名（对应 reference/ 下的 .json 文件名）")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if not args.model:
        output_error("--model 参数必填")
        return

    # 解析图片标识符为本地路径
    image_paths: List[str] = []
    if args.images:
        for ident in args.images.split(","):
            ident = ident.strip()
            if not ident:
                continue
            path = resolve_image_file(ident)
            if path:
                image_paths.append(path)
            else:
                output_error(f"未找到图片标识符: {ident}")
                return

    result = call_comfyui_generate(
        args.prompt,
        aspect_ratio=args.aspect_ratio,
        model_name=args.model,
        image_paths=image_paths if image_paths else None
    )

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
        model=args.model,
    )


if __name__ == "__main__":
    main()
