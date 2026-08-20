#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-08-18
Description: MiniMax H3 视频生成脚本（文生视频/图生视频），供 video_generation SKILL 调用

约定：
- 工作流 JSON 放在 skill 目录的 reference/ 下：h3_t2v.json / h3_i2v.json
- Prompt 占位符: {{prompt}}
- 图片占位符: {{input_image}}
- 尺寸占位符: {{width}} / {{height}}（按输入图比例自适应，32 对齐）
- 时长占位符: {{length}}（由 --duration 决定帧数）
- 分阶段执行：首次调用提交并等待，超时返回 prompt_id；LLM 可带 --prompt-id 续查（幂等）
"""
import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

# 复用 image_generation 技能的通用工具（HTTP / 图片解析 / 输出协议）
_IG_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "image_generation" / "scripts"
sys.path.insert(0, str(_IG_SCRIPTS))

from _common import (
    get_image_paths, resolve_image_file,
    read_image_file, http_post, http_get,
    output_result, output_error,
)
from comfyui_workflow_loader import (
    load_workflow, apply_prompt, apply_input_images,
)

# 工作流目录指向本技能自己的 reference/（loader 默认指向 image_generation 的）
import comfyui_workflow_loader as _wf_loader
_wf_loader.CONFIG_DIR = Path(__file__).resolve().parent.parent / "reference"

# 视频存储核心动态加载（与 _common.py 加载 _image_store_core 的模式一致）
_core_path = Path(os.environ.get("PROJECT_ROOT", ".")).resolve() / "hoshino" / "modules" / "aichat" / "aichat" / "_video_store_core.py"
if _core_path.exists():
    import importlib.util
    spec = importlib.util.spec_from_file_location("video_store_core", str(_core_path))
    video_store_core = importlib.util.module_from_spec(spec)
    sys.modules["video_store_core"] = video_store_core
    spec.loader.exec_module(video_store_core)
    VideoStoreCore = video_store_core.VideoStoreCore
else:
    raise RuntimeError(f"_video_store_core.py not found at {_core_path}")

COMFYUI_BASE_URL = os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188")

# 时长 → 帧数（24fps，H3 的 17k+5 网格：56≈2.3s, 124≈5.2s）
DURATION_FRAMES = {"2": 56, "5": 124}

# 任务名称 → 工作流文件名
TASK_WORKFLOW = {
    "t2v": "h3_t2v",   # MiniMax H3 文生视频（带音频，约 1-2 分钟）
    "i2v": "h3_i2v",   # MiniMax H3 图生视频（首帧锚定，约 1-2 分钟）
}


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
        raise RuntimeError(f"ComfyUI 上传图片失败 HTTP {result.get('status')}: {result.get('text', '')[:200]}")
    resp = result.get("json", {})
    filename = resp.get("name")
    if not filename:
        raise RuntimeError(f"ComfyUI 上传未返回文件名: {resp}")
    return filename


def apply_length(workflow: Dict[str, Any], frames: int) -> None:
    """将工作流中的 {{length}} 占位符替换为帧数（int）"""
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        for k, v in node.get("inputs", {}).items():
            if v == "{{length}}":
                node["inputs"][k] = frames


def apply_size(workflow: Dict[str, Any], width: int, height: int) -> None:
    """将工作流中的 {{width}}/{{height}} 占位符替换为分辨率（int）"""
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        for k, v in node.get("inputs", {}).items():
            if v in ("{{width}}", "{{height}}"):
                node["inputs"][k] = width if v == "{{width}}" else height


MAX_PIXELS = 864 * 480  # 目标分辨率像素量上限（16:9 基准，与显存预算匹配）


def compute_target_size(image_path: str, max_pixels: int = MAX_PIXELS,
                        alignment: int = 32) -> tuple:
    """按输入图宽高比计算目标分辨率（alignment 对齐，像素量不超过 max_pixels）

    MiniMax H3 的分辨率要求 32 倍数对齐；输入图与目标同比例时零变形。
    """
    from PIL import Image
    with Image.open(image_path) as img:
        w, h = img.size
    aspect = w / h
    scale = min((max_pixels / (w * h)) ** 0.5, 1.0)
    width = max(alignment, round(w * scale / alignment) * alignment)
    height = max(alignment, round(width / aspect / alignment) * alignment)
    # 面积超限时逐档回退（保持比例）
    while width * height > max_pixels * 1.1 and width > alignment and height > alignment:
        width -= alignment
        height = max(alignment, round(width / aspect / alignment) * alignment)
    return width, height


def submit_task(workflow: Dict[str, Any]) -> str:
    """提交工作流到 ComfyUI，返回 prompt_id"""
    base = COMFYUI_BASE_URL.rstrip("/")
    url = f"{base}/prompt"
    payload = {"prompt": workflow, "client_id": "video_generation_skill"}
    result = http_post(url, json_data=payload)
    if "error" in result:
        raise RuntimeError(f"提交失败: {result['error']}")
    if result.get("status", 0) not in (200,):
        raise RuntimeError(f"提交失败 HTTP {result.get('status')}: {result.get('text', '')[:300]}")
    resp = result.get("json", {})
    prompt_id = resp.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI 未返回 prompt_id: {resp}")
    return prompt_id


def poll_result(prompt_id: str, wait_seconds: int) -> Dict[str, Any]:
    """轮询 /history/{prompt_id}，返回结果字典

    Returns:
        {"status": "done", "data": bytes} / {"status": "error", "error": str} /
        {"status": "pending"}
    """
    base = COMFYUI_BASE_URL.rstrip("/")
    history_url = f"{base}/history/{prompt_id}"
    interval = 3
    elapsed = 0

    while elapsed < wait_seconds:
        time.sleep(interval)
        elapsed += interval

        hist_result = http_get(history_url)
        if "error" in hist_result:
            continue

        hist = hist_result.get("json", {})
        if not isinstance(hist, dict):
            continue

        entry = hist.get(prompt_id, {})
        if not entry:
            continue

        status = entry.get("status", {})

        # 执行错误
        for msg in status.get("messages", []):
            if msg[0] == "execution_error":
                detail = msg[1]
                return {
                    "status": "error",
                    "error": f"生成失败: {detail.get('exception_type', '')} "
                             f"{detail.get('exception_message', '')[:200]}",
                }

        outputs = entry.get("outputs", {})
        for node_id, node_output in outputs.items():
            # VHS_VideoCombine 输出 videos/gifs 字段
            for key in ("videos", "gifs"):
                items = node_output.get(key, [])
                for item in items:
                    filename = item.get("filename")
                    if not filename:
                        continue
                    subfolder = item.get("subfolder", "")
                    img_type = item.get("type", "output")
                    view_url = (
                        f"{base}/view?filename={quote(filename)}"
                        f"&subfolder={quote(subfolder)}&type={quote(img_type)}"
                    )
                    vid_resp = http_get(view_url)
                    if vid_resp.get("status") == 200:
                        content = vid_resp.get("content")
                        if content:
                            return {"status": "done", "data": content}
                        return {"status": "error", "error": "ComfyUI /view 未返回视频数据"}

        if status.get("completed") or status.get("status_str") == "success":
            return {"status": "error", "error": "任务完成但未找到视频输出"}

    return {"status": "pending"}


def store_video(data: bytes) -> Dict[str, Any]:
    """存储视频到会话 VideoStore，返回 {"identifier", "path"}"""
    session_id = os.environ.get("SESSION_ID", "unknown")
    store = VideoStoreCore(session_id)
    entry = store.store_bytes(data, "ai", "mp4")
    return {
        "identifier": entry.identifier,
        "path": str(entry.file_path),
        "format": entry.format,
        "size_bytes": entry.size_bytes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="ComfyUI 视频生成")
    parser.add_argument("--task", choices=["t2v", "i2v"], default="t2v", help="任务类型")
    parser.add_argument("--prompt", default="", help="视频描述（已调优）")
    parser.add_argument("--duration", choices=["2", "5"], default="2", help="时长（秒）")
    parser.add_argument("--images", default="", help="图生视频输入图标识符，逗号分隔")
    parser.add_argument("--prompt-id", default="", help="续查已提交任务的 prompt_id（幂等）")
    parser.add_argument("--wait", type=int, default=280, help="本次等待秒数（默认 280）")
    args = parser.parse_args()

    if args.prompt_id:
        # ---------- 续查阶段 ----------
        result = poll_result(args.prompt_id, args.wait)
        if result["status"] == "done":
            stored = store_video(result["data"])
            output_result(True, identifier=stored["identifier"], path=stored["path"],
                          model=f"h3_{args.task}")
        elif result["status"] == "error":
            output_error(result["error"])
        else:
            output_error(f"视频仍在生成中，请使用 --prompt-id {args.prompt_id} 继续查询")
        return

    # ---------- 提交阶段 ----------
    if not args.prompt:
        output_error("--prompt 参数必填")
        return

    workflow_name = TASK_WORKFLOW.get(args.task)
    if not workflow_name:
        output_error(f"不支持的任务类型: {args.task}")
        return

    try:
        wf = copy.deepcopy(load_workflow(workflow_name))
    except RuntimeError as e:
        output_error(str(e))
        return

    # 替换占位符
    apply_prompt(wf, args.prompt)
    apply_length(wf, DURATION_FRAMES[args.duration])

    if args.task == "i2v":
        image_paths: List[str] = []
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
        if not image_paths:
            output_error("图生视频需要提供 --images 图片标识符")
            return
        try:
            # 按首张输入图比例自适应分辨率（16:9 基准像素量上限）
            width, height = compute_target_size(image_paths[0])
            apply_size(wf, width, height)
            uploaded = [upload_image_to_comfyui(p) for p in image_paths]
        except Exception as e:
            output_error(f"图片上传失败: {e}")
            return
        apply_input_images(wf, uploaded)

    # 提交并等待
    try:
        prompt_id = submit_task(wf)
    except RuntimeError as e:
        output_error(str(e))
        return

    result = poll_result(prompt_id, args.wait)
    if result["status"] == "done":
        stored = store_video(result["data"])
        output_result(True, identifier=stored["identifier"], path=stored["path"],
                      model=f"h3_{args.task}")
    elif result["status"] == "error":
        output_error(result["error"])
    else:
        output_error(f"视频仍在生成中，请使用 --prompt-id {prompt_id} 继续查询")


if __name__ == "__main__":
    main()
