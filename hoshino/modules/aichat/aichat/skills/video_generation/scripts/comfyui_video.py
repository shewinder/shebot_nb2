#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-08-18
Description: MiniMax H3 视频生成脚本（文生视频/图生视频/角色参考），供 video_generation SKILL 调用

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

# 任务名称 → 工作流文件名
TASK_WORKFLOW = {
    "t2v": "h3_t2v",   # MiniMax H3 文生视频（带音频，约 1-2 分钟）
    "i2v": "h3_i2v",   # MiniMax H3 图生视频（首帧/尾帧锚定，约 1-2 分钟）
    "ref": "h3_refimg",  # MiniMax H3 角色参考模式（ref2va，无锚定，首帧自然+角色跟随）
}

# 融合模型（fl2va 基座 + ref2va 后段 adaln_proj）：单模型通吃 t2v/i2v/ref
TASK_WORKFLOW_HYBRID = {
    "t2v": "h3_t2v_hybrid",
    "i2v": "h3_i2v_hybrid",
    "ref": "h3_refimg_hybrid",
}

# H3 帧数网格：17k+5（24fps 下 124≈5.2s, 243≈10.1s）
H3_MIN_FRAMES = 5
H3_MAX_FRAMES = 362  # 官方训练范围 124-362（5-15 秒）

# 任务类型 → 默认采样步数（与对应加速 LoRA 规格匹配）
DEFAULT_STEPS = {
    "t2v": 8,   # turbo v4（4-8 步有效，8 步最稳）
    "i2v": 8,   # turbo v4（4-8 步有效，8 步最稳）
    "ref": 4,   # ref2v_turbo_4step
}


def duration_to_frames(duration: float) -> int:
    """秒数 → H3 帧数（snap 到 17k+5 网格）"""
    frames = max(H3_MIN_FRAMES, round(duration * 24))
    return 17 * round((frames - 5) / 17) + 5


def build_multi_guide_workflow(base_wf: Dict[str, Any], uploaded: List[str],
                               frame_count: int, guides: Optional[List[int]] = None,
                               start_nid: int = 100) -> None:
    """在基础 T2V 工作流上动态插入多图 AddGuide 锚定链（就地修改）

    - 每张图：一个 LoadImage 节点 + 一个 MiniMaxH3AddGuide 节点
    - AddGuide 链式：前一个的 positive 输出接下一个的 positive 输入
    - guides 缺省时：首图锚 0 帧、末图锚最后帧、中间图均匀分布
    - 返回后调用方需把 KSampler 的 positive 指向最后一个 AddGuide
    """
    if not uploaded:
        return None
    n = len(uploaded)
    if guides is None:
        if n == 1:
            frame_ids = [0]
        else:
            frame_ids = [round(i * (frame_count - 1) / (n - 1)) for i in range(n)]
    else:
        if len(guides) != n:
            raise RuntimeError(f"--guides 数量({len(guides)})必须与图片数({n})一致")
        frame_ids = [max(0, min(frame_count - 1, round(g * 24))) for g in guides]

    cond_node = "7"  # MiniMaxH3ImageToVideo 的 positive 输出
    latent_node = "7"
    for i, (fname, fidx) in enumerate(zip(uploaded, frame_ids)):
        img_nid = str(start_nid + i * 2)
        guide_nid = str(start_nid + i * 2 + 1)
        base_wf[img_nid] = {"class_type": "LoadImage", "inputs": {"image": fname}}
        base_wf[guide_nid] = {"class_type": "MiniMaxH3AddGuide", "inputs": {
            "positive": [cond_node, 0],
            "vae": ["3", 0],
            "latent": [latent_node, 1],
            "image": [img_nid, 0],
            "frame_idx": fidx,
        }}
        cond_node = guide_nid
    return cond_node


def _apply_anchors(wf: Dict[str, Any], first_name: Optional[str] = None,
                   last_name: Optional[str] = None) -> None:
    """填充 h3_i2v 工作流的首帧/尾帧锚位，并清理未用锚位节点"""
    if first_name:
        wf["13"]["inputs"]["image"] = first_name
    else:
        wf["7"]["inputs"].pop("first_frame", None)
        wf.pop("13", None)
    if last_name:
        wf["14"]["inputs"]["image"] = last_name
    else:
        wf["7"]["inputs"].pop("last_frame", None)
        wf.pop("14", None)


def _apply_ref_images(wf: Dict[str, Any], uploaded: List[str]) -> None:
    """按参考图数量重建 MiniMaxH3ReferenceToVideo 的 ref_images.ref_image_* 输入（就地修改）

    每张图一个 LoadImage 节点（从 id 15 起），ref_images.ref_image_i 指向对应节点。
    先清空工作流预置的 ref_images.ref_image_* 输入，避免残留引用缺失节点的输入。
    """
    for key in [k for k in wf["7"]["inputs"] if k.startswith("ref_images.ref_image_")]:
        del wf["7"]["inputs"][key]
    for i, fname in enumerate(uploaded):
        img_nid = str(15 + i)
        wf[img_nid] = {"class_type": "LoadImage", "inputs": {"image": fname}}
        wf["7"]["inputs"][f"ref_images.ref_image_{i}"] = [img_nid, 0]
    # 清理超出参考图数量的预置 LoadImage 节点（基础工作流只有 15/16）
    for j in range(len(uploaded), 16):
        wf.pop(str(15 + j), None)


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


def apply_steps(workflow: Dict[str, Any], steps: int) -> None:
    """将工作流中的 {{steps}} 占位符替换为采样步数（int）"""
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        for k, v in node.get("inputs", {}).items():
            if v == "{{steps}}":
                node["inputs"][k] = steps


# 两阶段 latent 超分：低清生成 -> 2x latent 放大 -> 精炼采样
LATENT_UPSCALE_MODEL = "minimax_h3_latent_upscaler_3d_bf16.safetensors"
LATENT_UPSCALE_REFINE_STEPS = 4
LATENT_UPSCALE_REFINE_DENOISE = 0.5
# 16GB 显存实测上限（输出像素）：t2v 1728×960(1.62M) 通过；i2v 896×1920(1.72M) OOM、832×1216(1.01M) 通过
LATENT_UPSCALE_MAX_PIXELS = {"t2v": 1650 * 1024, "i2v": 1300 * 1024, "ref": 1300 * 1024}


def apply_latent_upscale(workflow: Dict[str, Any], low_w: int, low_h: int,
                         prompt: str, length: int, scale: float = 2.0) -> None:
    """把生成工作流改造成两阶段 latent 超分（低清 latent 放大后精炼）

    语义：传入的 low_w/low_h 是低清生成档（--resolution 档或按图比例），
    输出 = 低清 × scale（32 对齐），与原生直出分辨率不同可区分。

    Phase 2 的 conditioning 必须按放大尺寸重编码（复用 Phase 1 的条件会导致
    布局行数与放大后 latent 不匹配，数值爆炸输出黑视频），故新建生成节点重编码
    条件（i2v 的首尾帧锚定、ref 的参考图随图保留）。

    采样链分流：turbo 工作流（t2v/i2v，节点 81）用 TurboSampler 精炼；
    ref 工作流（KSampler，节点 8）用 KSampler 精炼。
    """
    hi_w = round(low_w * scale / 32) * 32  # 放大后尺寸（Phase 2 全部节点以此为准）
    hi_h = round(low_h * scale / 32) * 32
    apply_size(workflow, low_w, low_h)
    # 占位符可能已被上游替换成最终尺寸，直接覆盖 Phase 1 生成节点
    workflow["7"]["inputs"]["width"] = low_w
    workflow["7"]["inputs"]["height"] = low_h

    workflow["90"] = {"class_type": "MinimaxH3LatentUpscaler3D", "inputs": {
        "latent": ["81", 0],
        "model_name": LATENT_UPSCALE_MODEL,
        "mode": "scale by multiplier",
        "mode.scale": scale,
        "align": 32,
        "enable_temporal_chunking": True,
        "force_unload": True,
        "device": "cuda",
        "precision": "bf16",
    }}

    if workflow.get("8", {}).get("class_type") == "KSampler":
        # ---- ref：ReferenceToVideo 重编码条件 + KSampler 精炼 ----
        workflow["90"]["inputs"]["latent"] = ["8", 0]
        cond_inputs = dict(workflow["7"]["inputs"])
        cond_inputs["prompt"] = prompt
        cond_inputs["width"] = hi_w
        cond_inputs["height"] = hi_h
        cond_inputs["length"] = length
        workflow["96"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": cond_inputs}
        refine = dict(workflow["8"]["inputs"])
        refine["positive"] = ["96", 0]
        refine["latent_image"] = ["90", 0]
        refine["steps"] = LATENT_UPSCALE_REFINE_STEPS
        refine["denoise"] = LATENT_UPSCALE_REFINE_DENOISE
        workflow["97"] = {"class_type": "KSampler", "inputs": refine}
        workflow["9"]["inputs"]["samples"] = ["97", 0]
        workflow["10"]["inputs"]["samples"] = ["97", 0]
        return

    # ---- t2v/i2v：ImageToVideo 重编码条件 + TurboSampler 精炼 ----
    # Phase 2 conditioning：按放大尺寸重编码（i2v 保留首尾帧锚定）
    cond_inputs = {
        "clip": ["2", 0], "vae": ["3", 0], "prompt": prompt,
        "width": hi_w, "height": hi_h, "length": length,
    }
    if "13" in workflow:  # i2v 首帧
        cond_inputs["first_frame"] = ["13", 0]
    if "14" in workflow:  # i2v 尾帧
        cond_inputs["last_frame"] = ["14", 0]
    workflow["96"] = {"class_type": "MiniMaxH3ImageToVideo", "inputs": cond_inputs}

    workflow["91"] = {"class_type": "MiniMaxH3TurboSampler", "inputs": {}}
    workflow["92"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": ["93", 0], "guider": ["94", 0], "sampler": ["91", 0],
        "sigmas": ["95", 0], "latent_image": ["90", 0]}}
    workflow["93"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": 20260917}}
    workflow["94"] = {"class_type": "BasicGuider", "inputs": {"model": ["6", 0], "conditioning": ["96", 0]}}
    workflow["95"] = {"class_type": "BasicScheduler", "inputs": {
        "model": ["6", 0], "scheduler": "simple",
        "steps": LATENT_UPSCALE_REFINE_STEPS, "denoise": LATENT_UPSCALE_REFINE_DENOISE}}
    # 解码改接 Phase 2 输出
    workflow["9"]["inputs"]["samples"] = ["92", 0]
    workflow["10"]["inputs"]["samples"] = ["92", 0]


# 分辨率档位 → 16:9 基准像素量上限
RESOLUTION_PIXELS = {
    "480p": 864 * 480,     # 快速档（默认）
    "768p": 1344 * 768,    # 高清档（约 3-5 倍耗时）
}
MAX_PIXELS = RESOLUTION_PIXELS["480p"]


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


def compute_size_for_aspect(aspect: str, max_pixels: int = MAX_PIXELS,
                            alignment: int = 32) -> tuple:
    """按宽高比字符串（如 16:9 / 9:16 / 3:4 / 1:1）计算目标分辨率

    不依赖任何输入图：面积逼近 max_pixels，32 对齐。
    """
    try:
        w_ratio, h_ratio = aspect.lower().replace("：", ":").split(":")
        w_ratio, h_ratio = float(w_ratio), float(h_ratio)
    except (ValueError, AttributeError):
        raise RuntimeError(f"--aspect-ratio 格式应为 W:H（如 16:9、9:16、3:4、1:1），收到: {aspect}")
    if w_ratio <= 0 or h_ratio <= 0:
        raise RuntimeError(f"--aspect-ratio 数值必须为正: {aspect}")
    scale = (max_pixels / (w_ratio * h_ratio)) ** 0.5
    width = max(alignment, round(w_ratio * scale / alignment) * alignment)
    height = max(alignment, round(h_ratio * scale / alignment) * alignment)
    # 面积超限时逐档回退（保持比例）
    while width * height > max_pixels * 1.1 and width > alignment and height > alignment:
        width -= alignment
        height = max(alignment, round(width * h_ratio / w_ratio / alignment) * alignment)
    return width, height


def free_gpu_memory() -> None:
    """提交前释放 ComfyUI 显存缓存（任务完成后模型驻留显存，累积会导致下个任务 OOM）"""
    base = COMFYUI_BASE_URL.rstrip("/")
    try:
        http_post(f"{base}/free", json_data={"unload_models": True, "free_memory": True})
    except Exception:
        pass  # 释放失败不阻塞提交，让 ComfyUI 自行处理


def submit_task(workflow: Dict[str, Any]) -> str:
    """提交工作流到 ComfyUI，返回 prompt_id"""
    free_gpu_memory()
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
    consecutive_failures = 0

    while elapsed < wait_seconds:
        time.sleep(interval)
        elapsed += interval

        # 探测用短超时（默认 300s 太久）：失联时快速失败，避免 LLM 长时间收到"未完成"
        hist_result = http_get(history_url, timeout=10)
        if "error" in hist_result:
            # ComfyUI 失联（进程挂掉/网络断）：任务已无法恢复，不继续空等到超时
            consecutive_failures += 1
            if consecutive_failures >= 3:  # 约 9 秒连续失联即判定任务丢失
                return {"status": "error",
                        "error": f"ComfyUI 失联（{hist_result['error'][:100]}），任务已丢失，请确认 ComfyUI 后重新生成"}
            continue
        consecutive_failures = 0

        hist = hist_result.get("json", {})
        if not isinstance(hist, dict):
            continue

        entry = hist.get(prompt_id, {})
        if not entry:
            # 不在历史：查队列是否仍在执行/排队；都不在 = 任务已丢失（如服务器重启）
            q_result = http_get(f"{base}/queue", timeout=10)
            q = q_result.get("json", {}) if q_result.get("status") == 200 else {}
            in_queue = any(
                prompt_id in (item[1] if isinstance(item, list) and len(item) > 1 else ())
                for item in q.get("queue_running", []) + q.get("queue_pending", [])
            )
            if not in_queue:
                return {"status": "error",
                        "error": "任务已丢失（ComfyUI 可能重启过），请重新生成"}
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
                    vid_resp = http_get(view_url, timeout=60)
                    if vid_resp.get("status") == 200:
                        content = vid_resp.get("content")
                        if content:
                            return {"status": "done", "data": content}
                        return {"status": "error", "error": "ComfyUI /view 未返回视频数据"}

            # comfy-core SaveVideo：images + animated:[true]（视频以 mp4 存于 output/）
            if node_output.get("animated") == [True]:
                for item in node_output.get("images", []):
                    filename = item.get("filename")
                    if not filename:
                        continue
                    subfolder = item.get("subfolder", "")
                    img_type = item.get("type", "output")
                    view_url = (
                        f"{base}/view?filename={quote(filename)}"
                        f"&subfolder={quote(subfolder)}&type={quote(img_type)}"
                    )
                    vid_resp = http_get(view_url, timeout=60)
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
    parser.add_argument("--task", choices=["t2v", "i2v", "ref"], default="t2v", help="任务类型")
    parser.add_argument("--model", choices=["hybrid", "official"], default="hybrid",
                        help="模型版本：hybrid=融合模型（默认），official=官方 fl2va/ref2va")
    parser.add_argument("--latent-upscale", action="store_true",
                        help="两阶段 latent 超分（t2v/i2v/ref）：低清生成->latent 放大->精炼，直接产出高清")
    parser.add_argument("--latent-scale", type=float, default=2.0,
                        help="latent 放大倍数（默认 2；范围由 upscaler 节点校验 1-4）")
    parser.add_argument("--prompt", default="", help="视频描述（已调优）")
    parser.add_argument("--duration", type=float, default=2.0,
                        help="时长（秒，1-15，默认 2）")
    parser.add_argument("--resolution", choices=list(RESOLUTION_PIXELS.keys()), default="480p",
                        help="分辨率档位（默认 480p 快速；768p 高清约 3-5 倍耗时）")
    parser.add_argument("--images", default="", help="输入图标识符，逗号分隔（i2v=锚定图；ref=角色参考图）")
    parser.add_argument("--guides", default="", help="多图锚定时间点（秒，逗号分隔，须与图片数一致；缺省自动均分）")
    parser.add_argument("--anchor", choices=["first", "last"], default="first",
                        help="单图锚定位置（首帧/尾帧，默认首帧）")
    parser.add_argument("--aspect-ratio", default="",
                        help="目标宽高比（如 16:9、9:16、3:4、1:1；ref 模式指定时视频画幅不再跟随参考图比例）")
    parser.add_argument("--steps", type=int, default=0,
                        help="采样步数（默认按任务：ref=4、t2v/i2v=8，与加速 LoRA 规格匹配）")
    parser.add_argument("--lora-strength", type=float, default=0.5,
                        help="MysticXXX LoRA 强度（t2v/i2v 生效；0 = 关闭该 LoRA 节点，默认 0.5）")
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

    workflow_name = (TASK_WORKFLOW_HYBRID if args.model == "hybrid" else TASK_WORKFLOW).get(args.task)
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
    if not 1.0 <= args.duration <= 15.0:
        output_error("时长仅支持 1-15 秒")
        return
    apply_length(wf, duration_to_frames(args.duration))

    # 采样步数：显式指定优先，否则按任务默认（与加速 LoRA 规格匹配）
    steps = args.steps if args.steps > 0 else DEFAULT_STEPS.get(args.task, 8)
    apply_steps(wf, steps)

    # MysticXXX LoRA：t2v/i2v 工作流带节点 70；强度 0 时关闭（SigmaShift 绕过 70 直连 turbo）
    if "70" in wf and wf["70"].get("class_type") == "LoraLoaderModelOnly":
        if args.lora_strength <= 0:
            # 节点6(SigmaShift) 的 model 原指向 70，改为指向 turbo LoRA 节点5
            wf["6"]["inputs"]["model"] = ["5", 0]
            wf.pop("70", None)
        else:
            wf["70"]["inputs"]["strength_model"] = args.lora_strength

    # 分辨率：t2v 用档位 16:9 基准；i2v 按输入图比例自适应（上限随档位）
    # latent 超分：--resolution 作为低清生成档，输出 = 低清 × --latent-scale；--latent-upscale 是独立开关
    eff_resolution = args.resolution
    max_pixels = RESOLUTION_PIXELS[eff_resolution]
    final_w = final_h = 0  # 输出尺寸：普通生成=最终尺寸；latent 超分=低清档（输出为低清 × scale）

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
            # 按首张输入图比例自适应分辨率（像素量上限随档位）
            width, height = compute_target_size(image_paths[0], max_pixels=max_pixels)
            uploaded = [upload_image_to_comfyui(p) for p in image_paths]
        except Exception as e:
            output_error(f"图片上传失败: {e}")
            return

        guides: Optional[List[float]] = None
        if args.guides:
            guides = []
            for g in args.guides.split(","):
                g = g.strip()
                if not g:
                    continue
                try:
                    guides.append(float(g))
                except ValueError:
                    output_error(f"--guides 含非法数值: {g}")
                    return

        multi = len(uploaded) > 1 or guides is not None
        if multi:
            # 多图多帧锚定：以 h3_t2v 为基础动态构造 AddGuide 链
            try:
                wf = copy.deepcopy(load_workflow("h3_t2v"))
            except RuntimeError as e:
                output_error(str(e))
                return
            apply_prompt(wf, args.prompt)
            apply_length(wf, duration_to_frames(args.duration))
            apply_size(wf, width, height)
            apply_steps(wf, steps)
            frame_count = duration_to_frames(args.duration)
            try:
                last_guide = build_multi_guide_workflow(wf, uploaded, frame_count, guides)
            except RuntimeError as e:
                output_error(str(e))
                return
            # 多图锚定：AddGuide 链接 BasicGuider(83) 的 conditioning
            wf["83"]["inputs"]["conditioning"] = [last_guide, 0]
        else:
            final_w, final_h = width, height
            if len(uploaded) == 2:
                # 两张图：原生首尾帧（FLF2V）
                apply_size(wf, width, height)
                _apply_anchors(wf, first_name=uploaded[0], last_name=uploaded[1])
            else:
                # 单图：按 --anchor 指定首帧或尾帧锚定
                apply_size(wf, width, height)
                if args.anchor == "first":
                    _apply_anchors(wf, first_name=uploaded[0])
                else:
                    _apply_anchors(wf, last_name=uploaded[0])
    elif args.task == "ref":
        # 角色参考模式（ref2va）：多图作 <Picture N> 参考，无锚定，首帧自然
        image_paths = []
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
            output_error("角色参考模式需要提供 --images 参考图标识符")
            return
        try:
            if args.aspect_ratio:
                # 显式指定画幅：视频宽高不跟随参考图（拼接图比例不会被带入）
                width, height = compute_size_for_aspect(args.aspect_ratio, max_pixels=max_pixels)
            else:
                width, height = compute_target_size(image_paths[0], max_pixels=max_pixels)
            uploaded = [upload_image_to_comfyui(p) for p in image_paths]
        except Exception as e:
            output_error(f"图片上传失败: {e}")
            return
        apply_size(wf, width, height)
        final_w, final_h = width, height
        _apply_ref_images(wf, uploaded)
    else:
        # t2v：档位 16:9 基准尺寸（32 对齐）
        base_sizes = {"480p": (864, 480), "768p": (1344, 768)}
        final_w, final_h = base_sizes[eff_resolution]
        apply_size(wf, *base_sizes[eff_resolution])

    # 两阶段 latent 超分（t2v/i2v/ref；多图 AddGuide 暂不支持；仅 480p 低清档）
    if args.latent_upscale:
        if args.task not in ("t2v", "i2v", "ref"):
            output_error("--latent-upscale 仅支持 t2v/i2v/ref")
            return
        if args.task == "i2v" and multi:
            output_error("--latent-upscale 暂不支持多图多帧锚定（AddGuide）")
            return
        hi_w = round(final_w * args.latent_scale / 32) * 32
        hi_h = round(final_h * args.latent_scale / 32) * 32
        limit = LATENT_UPSCALE_MAX_PIXELS[args.task]
        if hi_w * hi_h > limit:
            output_error(f"--latent-upscale 输出 {hi_w}×{hi_h} 超过 16GB 显存上限"
                         f"（{args.task} 任务上限 {limit // 1024}K 像素）；请降低 --latent-scale 或换更小的图")
            return
        apply_latent_upscale(wf, final_w, final_h, args.prompt,
                             duration_to_frames(args.duration), args.latent_scale)

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
