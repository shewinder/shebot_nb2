#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-08-23
Description: MiniMax H3 统一链式长视频生成，供 video_generation SKILL 调用

原理（参考 MacroSony/minimax-h3-chained-character-swap）：
- 支持 t2v / i2v / fl2v / ref / edit，共用逐场景计划和续跑协议
- 段 1 无上下文，后续段使用 ChainContext
- 每段以上一段交付视频的尾部 22 帧为 Motion Context（ChainContext 编码为
  latent token 钉在下一段时间轴头部），raw 输出前 22 帧为 context 复刻，
  由工作流内 LoopTrim 裁除，交付段可直接拼接
- 彩噪 taper 注入（--noise on，默认）：context 前 19 帧 @0.45 注噪 +
  末 3 帧渐弱到 0.10，触发模型修复模式，防链式锐度衰减（实测 +8-9%）
- 生成音频与画面一起裁切、保存和拼接，后续段同时继承音画上下文
- edit 模式可以在最终拼接后恢复源视频音轨

约定：
- 场景计划: --plan-json（JSON 数组，每项含 prompt / length / 可选 seed）
- 图片: --images（i2v=1 张，fl2v=2 张，ref/edit=1-4 张）
- 源视频: --source-video（仅 edit 模式，作 <Video 1>）
"""
import argparse
import copy
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
# _common.py 位于 image_generation/scripts（与 comfyui_video.py 同一约定）
sys.path.insert(0, str(_SCRIPT_DIR.parent.parent / "image_generation" / "scripts"))

from _common import (  # noqa: E402
    resolve_image_file,
    output_result,
    output_error,
)
from comfyui_workflow_loader import (  # noqa: E402
    load_workflow, apply_prompt,
)
from comfyui_video import (  # noqa: E402
    COMFYUI_BASE_URL, RESOLUTION_PIXELS, VideoStoreCore, H3_MIN_FRAMES, H3_MAX_FRAMES,
    compute_target_size, compute_size_for_aspect,
    upload_image_to_comfyui, submit_task, poll_result,
    store_video, apply_length, apply_size, http_post, model_checkpoint,
)

# 链式工作流文件名（reference/ 下）
CHAIN_WORKFLOWS = {
    "initial": "h3_chain_initial",   # 段 1：无 context
    "segment": "h3_chain_segment",   # 续写段：22 帧 Motion Context + LoopTrim
}

IMAGE_WORKFLOWS = {
    "t2v": "h3_t2v",
    "i2v": "h3_i2v",
    "fl2v": "h3_i2v",
}

TASKS = ("t2v", "i2v", "fl2v", "ref", "edit")

CONTEXT_FRAMES = 22  # Motion Context 帧数（与工作流 ChainPlan context_length 一致）

# 彩噪注入参数（仓库验证的 T3 taper 配方）
NOISE_ALPHA = 0.45
NOISE_ALPHA_END = 0.10
NOISE_RAMP_FRAMES = 3
NOISE_GRID = (36, 64)
NOISE_PALETTE = [
    (185, 115, 215), (115, 195, 140), (150, 148, 162),
    (205, 150, 192), (138, 182, 148), (160, 120, 175),
]

FRAME_RATE = 24


def find_ffmpeg() -> Optional[str]:
    """探测 ffmpeg：系统 PATH"""
    return shutil.which("ffmpeg")


def upload_video_to_comfyui(video_path: str) -> str:
    """上传视频到 ComfyUI input 目录，返回文件名"""
    base = COMFYUI_BASE_URL.rstrip("/")
    url = f"{base}/upload/image"
    data = Path(video_path).read_bytes()
    files = {"image": (Path(video_path).name, data, "video/mp4")}
    result = http_post(url, files=files)
    if "error" in result:
        raise RuntimeError(f"上传视频到 ComfyUI 失败: {result['error']}")
    if result.get("status", 0) not in (200,):
        raise RuntimeError(f"ComfyUI 上传视频失败 HTTP {result.get('status')}: {result.get('text', '')[:200]}")
    resp = result.get("json", {})
    filename = resp.get("name")
    if not filename:
        raise RuntimeError(f"ComfyUI 上传未返回文件名: {resp}")
    return filename


def _alpha_for(position: int, tail: int, alpha: float, alpha_end: float, ramp: int) -> float:
    """注入强度：末 ramp 帧线性渐弱到 alpha_end"""
    from_end = tail - 1 - position
    if from_end >= ramp:
        return alpha
    return alpha + (alpha_end - alpha) * (ramp - from_end) / ramp


# ---------- 源视频预处理（角色替换模式） ----------

# 每段源窗口帧数（H3 网格值 17*7+5=124，含与上一段重叠的 22 帧）
SOURCE_WINDOW_FRAMES = 124
SOURCE_OVERLAP_FRAMES = CONTEXT_FRAMES  # 22：相邻段源窗口重叠区（与 context 帧数一致）


def run_ffmpeg(ffmpeg: str, cmd: List[str], desc: str) -> None:
    """执行 ffmpeg，失败抛异常"""
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"{desc}失败: {e.stderr.decode('utf-8', 'replace')[-300:]}")


def convert_to_24fps(ffmpeg: str, src: Path, out_path: Path) -> None:
    """源视频转 24fps（去音轨，保持时长与画面）"""
    run_ffmpeg(ffmpeg, [
        ffmpeg, "-y", "-v", "error", "-i", str(src),
        "-vf", "fps=24", "-c:v", "libx264", "-crf", "18", "-an",
        str(out_path),
    ], "源视频转 24fps")


def slice_source_window(ffmpeg: str, src_24fps: Path, start_frame: int,
                        window_frames: int, out_path: Path) -> None:
    """从 24fps 源视频按帧窗口切片（精确帧级，含音频丢弃）"""
    run_ffmpeg(ffmpeg, [
        ffmpeg, "-y", "-v", "error", "-i", str(src_24fps),
        "-vf", f"trim=start_frame={start_frame}:end_frame={start_frame + window_frames},"
               f"setpts=PTS-STARTPTS",
        "-c:v", "libx264", "-crf", "18", "-an",
        str(out_path),
    ], "源视频切帧窗口")


def probe_video_size(ffmpeg: str, video: Path) -> tuple:
    """抽首帧 PNG 读取视频分辨率"""
    with tempfile.TemporaryDirectory(prefix="h3probe_") as td:
        frame = Path(td) / "first.png"
        run_ffmpeg(ffmpeg, [
            ffmpeg, "-y", "-v", "error", "-i", str(video),
            "-frames:v", "1", str(frame),
        ], "视频尺寸探测")
        with Image.open(frame) as img:
            return img.size


def compute_target_size_wh(width: int, height: int, max_pixels: int,
                           alignment: int = 32) -> tuple:
    """按宽高比计算目标分辨率（32 对齐，像素量尽量吃满 max_pixels，允许放大）

    源分辨率低于档位上限时放大到档位面积（如 720×960 → 864×1152），
    提升清晰度；H3 官方 768p 档面积（~1MP）内安全。
    """
    aspect = width / height
    scale = (max_pixels / (width * height)) ** 0.5
    out_w = max(alignment, round(width * scale / alignment) * alignment)
    out_h = max(alignment, round(out_w / aspect / alignment) * alignment)
    while out_w * out_h > max_pixels * 1.1 and out_w > alignment and out_h > alignment:
        out_w -= alignment
        out_h = max(alignment, round(out_w / aspect / alignment) * alignment)
    return out_w, out_h


def plan_source_windows(total_frames: int) -> List[tuple]:
    """按仓库窗口规划源切分：段 i 起点 = (i-1)*102，窗口 124 帧

    末段不足 124 帧时对齐到 H3 帧网格（17k+5，向下取最近网格值）。
    """
    step = SOURCE_WINDOW_FRAMES - SOURCE_OVERLAP_FRAMES
    windows: List[tuple] = []
    start = 0
    while start < total_frames:
        remaining = total_frames - start
        window = min(SOURCE_WINDOW_FRAMES, remaining)
        if remaining < SOURCE_WINDOW_FRAMES:
            # 末段对齐到 H3 网格（17k+5），向下取整
            window = 17 * ((window - 5) // 17) + 5
            # 续写段会裁掉 22 帧 context，尾段不足一个有效输出段时直接丢弃，
            # 避免提交后得到空视频。
            min_window = H3_MIN_FRAMES if not windows else CONTEXT_FRAMES + H3_MIN_FRAMES
            if window < min_window:
                break
        windows.append((start, window))
        if remaining <= SOURCE_WINDOW_FRAMES:
            break
        start += step
    return windows


def count_frames(ffmpeg: str, video: Path) -> int:
    """统计视频总帧数（抽帧计数）"""
    with tempfile.TemporaryDirectory(prefix="h3count_") as td:
        pattern = Path(td) / "f_%04d.png"
        run_ffmpeg(ffmpeg, [
            ffmpeg, "-y", "-v", "error", "-i", str(video), str(pattern),
        ], "帧数统计")
        return len(list(Path(td).glob("f_*.png")))


def prepare_context(ffmpeg: str, src_video: Path, tail: int,
                    noise_on: bool, out_path: Path, seed: int) -> None:
    """从交付视频提取尾部 tail 帧和音频，重编码为上下文视频。

    步骤：ffmpeg 抽全部帧 → 保留尾部 tail 帧 →（noise_on）PIL 注入色块 → 重编码
    """
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="h3ctx_") as td:
        tmp = Path(td)
        pattern = tmp / "f_%04d.png"
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-i", str(src_video), str(pattern)],
            check=True, capture_output=True,
        )
        files = sorted(tmp.glob("f_*.png"))
        if len(files) < tail:
            raise RuntimeError(f"交付视频帧数({len(files)})不足 {tail} 帧")
        keep = files[-tail:]

        if noise_on:
            small = Image.new("RGB", NOISE_GRID)
            pixels = small.load()
            for y in range(NOISE_GRID[1]):
                for x in range(NOISE_GRID[0]):
                    pixels[x, y] = rng.choice(NOISE_PALETTE)
            with Image.open(keep[0]) as first:
                noisy_template = small.resize(first.size, Image.Resampling.NEAREST)
            for i, frame_path in enumerate(keep):
                amount = _alpha_for(i, tail, NOISE_ALPHA, NOISE_ALPHA_END, NOISE_RAMP_FRAMES)
                with Image.open(frame_path) as opened:
                    frame = opened.convert("RGB")
                Image.blend(frame, noisy_template, amount).save(frame_path)

        # 重命名连续序号后重编码，并保留同一时间窗的音频。
        keep_dir = tmp / "keep"
        keep_dir.mkdir()
        for i, f in enumerate(keep, 1):
            shutil.copy2(f, keep_dir / f"k_{i:04d}.png")
        tail_seconds = tail / float(FRAME_RATE)
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-framerate", str(FRAME_RATE),
             "-i", str(keep_dir / "k_%04d.png"),
             "-sseof", str(-tail_seconds),
             "-i", str(src_video), "-map", "0:v", "-map", "1:a?",
             "-frames:v", str(tail), "-af", f"atrim=duration={tail_seconds}",
             "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p",
             "-c:a", "aac", str(out_path)],
            check=True, capture_output=True,
        )


def _replace_scalar(wf: Dict[str, Any], placeholder: str, value: Any) -> None:
    """把工作流中的标量占位符替换为值（int/float/str）"""
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        for k, v in node.get("inputs", {}).items():
            if v == placeholder:
                node["inputs"][k] = value


def apply_chain_params(wf: Dict[str, Any], prompt: str, length: int,
                       steps: int, seed: int) -> None:
    """填充链式工作流的 plan_json（ChainPlan 配置节点）"""
    raw = wf["100"]["inputs"]["plan_json"]
    plan = json.loads(raw)
    plan["shots"][0]["prompt"] = prompt
    plan["shots"][0]["length"] = length
    plan["shots"][0]["steps"] = steps
    plan["shots"][0]["seed"] = seed
    wf["100"]["inputs"]["plan_json"] = json.dumps(plan, ensure_ascii=False)
    _replace_scalar(wf, "{{seed}}", seed)


def apply_identity_images(wf: Dict[str, Any], uploaded: List[str]) -> None:
    """按身份图数量重建 ref_image_* 输入链

    工作流预置 4 个 LoadImage 节点：40/41/42（前 3 张）+ 50（第 4 张特写），
    第 4 张必须用 50 号节点（43 是源视频 LoadVideo，不可占用）。
    ComfyUI 0.33 Ref2VA 的 AUTOGROW 输入名为 ref_image_N（不是 ref_images.ref_image_N）。
    """
    # 清空预置的 ref_images.ref_image_N 输入，按实际数量重建
    # 注意：ref_image_size 也以 ref_image 开头，必须排除；AUTOGROW 输入名带前缀
    for key in [k for k in wf["20"]["inputs"] if k.startswith("ref_images.ref_image_")]:
        del wf["20"]["inputs"][key]
    for i, fname in enumerate(uploaded):
        img_nid = str(40 + i) if i < 3 else "50"
        wf[img_nid] = {"class_type": "LoadImage", "inputs": {"image": fname}}
        wf["20"]["inputs"][f"ref_images.ref_image_{i}"] = [img_nid, 0]
    for j in range(len(uploaded), 3):
        wf.pop(str(40 + j), None)
    if len(uploaded) < 4:
        wf.pop("50", None)


def apply_source_video(wf: Dict[str, Any], source_name: Optional[str]) -> None:
    """源视频：有则填 LoadVideo 43；无则移除 ref_videos.ref_video_0 引用与 43/49 节点"""
    if source_name:
        wf["43"]["inputs"]["file"] = source_name
        return
    wf["20"]["inputs"].pop("ref_videos.ref_video_0", None)
    wf.pop("43", None)
    wf.pop("49", None)


def apply_generated_audio_output(wf: Dict[str, Any], continuation: bool) -> None:
    """解码 H3 音频，并与当前交付画面一起输出。"""
    latent_node = "81"  # turbo 链 SCA 输出
    decode_node = "109" if continuation else "21"
    output_node = "108" if continuation else "19"
    wf[decode_node] = {
        "class_type": "VAEDecodeAudio",
        "inputs": {"samples": [latent_node, 0], "vae": ["4", 0]},
    }
    if continuation:
        wf["106"]["inputs"].update({
            "audio": [decode_node, 0],
            "fps": float(FRAME_RATE),
            "match_tail": True,
        })
        images = ["106", 0]
        audio = ["106", 1]
    else:
        images = ["17", 0]
        audio = [decode_node, 0]
    wf[output_node] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": images,
            "audio": audio,
            "frame_rate": FRAME_RATE,
            "loop_count": 0,
            "filename_prefix": "h3_chain_bot/delivered_seg",
            "format": "video/h264-mp4",
            "pingpong": False,
            "save_output": True,
        },
    }
    if continuation:
        wf.pop("107", None)
    else:
        wf.pop("18", None)


def adapt_image_conditioning(wf: Dict[str, Any], task: str,
                             uploaded: List[str], seg_idx: int,
                             segments_total: int) -> None:
    """把 Ref2VA 链模板适配为 T2VA/I2VA/FL2VA。"""
    base = load_workflow(IMAGE_WORKFLOWS[task])
    wf["1"] = copy.deepcopy(base["1"])
    wf["5"] = copy.deepcopy(base["5"])
    wf["70"] = copy.deepcopy(base["70"])
    wf["61"]["inputs"]["model"] = ["70", 0]
    wf.pop("60", None)
    inputs: Dict[str, Any] = {
        "clip": ["2", 0],
        "vae": ["3", 0],
        "prompt": wf["20"]["inputs"]["prompt"],
        "width": wf["20"]["inputs"]["width"],
        "height": wf["20"]["inputs"]["height"],
        "length": wf["20"]["inputs"]["length"],
    }
    for node_id in ("40", "41", "42", "43", "49", "50"):
        wf.pop(node_id, None)
    if task in ("i2v", "fl2v") and seg_idx == 1:
        wf["40"] = {"class_type": "LoadImage", "inputs": {"image": uploaded[0]}}
        inputs["first_frame"] = ["40", 0]
    if task == "fl2v" and seg_idx == segments_total:
        wf["41"] = {"class_type": "LoadImage", "inputs": {"image": uploaded[1]}}
        inputs["last_frame"] = ["41", 0]
    wf["20"] = {"class_type": "MiniMaxH3ImageToVideo", "inputs": inputs}


def concat_videos(ffmpeg: str, paths: List[Path], out_path: Path) -> None:
    """ffmpeg concat 拼接视频和生成音频。"""
    list_file = out_path.parent / "concat.txt"
    list_file.write_text("".join(f"file '{p}'\n" for p in paths), encoding="utf-8")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
             "-map", "0:v:0", "-map", "0:a:0?", "-fps_mode", "passthrough",
             "-c:v", "libx264",
             "-preset", "fast", "-crf", "20", "-c:a", "aac",
             "-movflags", "+faststart", "-shortest", str(out_path)],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        detail = e.stderr.decode("utf-8", "replace")[-400:] if e.stderr else ""
        raise RuntimeError(f"拼接失败(exit {e.returncode}): {detail}")


# ---------- 无本地状态续跑 ----------

STATE_VERSION = 2
RUN_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def _is_valid_h3_length(value: int) -> bool:
    return H3_MIN_FRAMES <= value <= H3_MAX_FRAMES and (value - 5) % 17 == 0


def _parse_plan(raw: str) -> List[Dict[str, Any]]:
    """解析统一场景计划；每个场景拥有独立提示词、长度和可选 seed。"""
    if not raw:
        raise ValueError("必须提供 --plan-json")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--plan-json 不是有效 JSON: {exc.msg}") from exc
    if isinstance(value, dict):
        value = value.get("scenes")
    if not isinstance(value, list):
        raise ValueError("--plan-json 必须是场景数组或包含 scenes 数组的对象")
    if not 1 <= len(value) <= 10:
        raise ValueError("场景数仅支持 1-10 段")
    scenes: List[Dict[str, Any]] = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict) or not isinstance(item.get("prompt"), str):
            raise ValueError(f"场景 {index} 必须包含非空 prompt")
        prompt = item["prompt"].strip()
        if not prompt:
            raise ValueError(f"场景 {index} prompt 不能为空")
        length = item.get("length")
        if isinstance(length, bool) or not isinstance(length, int):
            raise ValueError(f"场景 {index} length 必须是整数帧数")
        if not _is_valid_h3_length(length):
            raise ValueError(
                f"场景 {index} length 必须是 {H3_MIN_FRAMES}-{H3_MAX_FRAMES} 内的 17k+5 帧")
        scene_seed = item.get("seed")
        if scene_seed is not None and (
                isinstance(scene_seed, bool) or not isinstance(scene_seed, int)
                or not 0 <= scene_seed < 2 ** 64):
            raise ValueError(f"场景 {index} seed 必须是 uint64 整数")
        scenes.append({
            "prompt": prompt,
            "length": length,
            "seed": scene_seed,
        })
    return scenes


def _state_video_path(store: VideoStoreCore, identifier: Any, field: str) -> Path:
    """从当前会话的视频存储解析 state 中的标识符"""
    if not isinstance(identifier, str):
        raise ValueError(f"state.{field} 必须是视频标识符")
    path = store.get_file_path(identifier)
    if not path:
        raise ValueError(f"state.{field} 对应的视频不存在或不属于当前会话")
    return path


def _validate_state(raw: str, session_id: str) -> Dict[str, Any]:
    """校验 LLM 原样回传的续跑 state"""
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"--state 不是有效 JSON: {e.msg}")
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        raise ValueError("--state 版本不支持")
    if state.get("session_id") != session_id:
        raise ValueError("state 不属于当前会话")
    if not RUN_ID_RE.fullmatch(str(state.get("run_id", ""))):
        raise ValueError("state.run_id 非法")
    total = state.get("segments_total")
    done = state.get("segments_done")
    if (isinstance(total, bool) or isinstance(done, bool)
            or not isinstance(total, int) or not isinstance(done, int)
            or not 1 <= total <= 10 or not 0 <= done <= total):
        raise ValueError("state 分段进度非法")
    task = state.get("task")
    if task not in TASKS:
        raise ValueError("state.task 非法")
    for field in ("width", "height", "steps"):
        value = state.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"state.{field} 非法")
    if state["width"] <= 0 or state["height"] <= 0 or state["steps"] <= 0:
        raise ValueError("state 视频尺寸或采样步数非法")
    if state.get("noise") not in ("on", "off"):
        raise ValueError("state.noise 非法")
    if state.get("model") not in ("hybrid", "official"):
        raise ValueError("state.model 非法")
    for field in ("no_lora", "legacy_sampler", "keep_audio"):
        if not isinstance(state.get(field), bool):
            raise ValueError(f"state.{field} 非法")
    scenes = state.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != total:
        raise ValueError("state.scenes 与分段数不一致")
    for index, scene in enumerate(scenes, 1):
        if (not isinstance(scene, dict)
                or not isinstance(scene.get("prompt"), str)
                or not scene["prompt"].strip()):
            raise ValueError(f"state.scenes[{index - 1}].prompt 非法")
        for field in ("length", "seed"):
            value = scene.get(field)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"state.scenes[{index - 1}].{field} 非法")
        if not _is_valid_h3_length(scene["length"]):
            raise ValueError(f"state.scenes[{index - 1}].length 非法")
        if index > 1 and scene["length"] < CONTEXT_FRAMES + H3_MIN_FRAMES:
            raise ValueError(f"state.scenes[{index - 1}].length 不足以承载上下文")
        if not 0 <= scene["seed"] < 2 ** 64:
            raise ValueError(f"state.scenes[{index - 1}].seed 非法")
    if (not isinstance(state.get("delivered"), list)
            or len(state["delivered"]) != done
            or any(not isinstance(identifier, str) or not identifier.strip()
                   for identifier in state["delivered"])):
        raise ValueError("state.delivered 与进度不一致")
    prompt_id = state.get("current_prompt_id")
    if (prompt_id is not None
            and (not isinstance(prompt_id, str) or not prompt_id.strip())):
        raise ValueError("state.current_prompt_id 非法")
    if done == total and prompt_id is not None:
        raise ValueError("已完成任务不能保留 current_prompt_id")
    uploaded = state.get("uploaded_images")
    if (not isinstance(uploaded, list)
            or any(not isinstance(image, str) or not image.strip()
                   for image in uploaded)):
        raise ValueError("state.uploaded_images 非法")
    expected_images = {"t2v": 0, "i2v": 1, "fl2v": 2}
    if task in expected_images and len(uploaded) != expected_images[task]:
        raise ValueError(f"state.{task} 图片数量非法")
    if task in ("ref", "edit") and not 1 <= len(uploaded) <= 4:
        raise ValueError(f"state.{task} 需要 1-4 张参考图")
    if task != "edit" and state["keep_audio"]:
        raise ValueError("仅 edit state 可以保留源音轨")
    source_windows = state.get("source_windows")
    if source_windows is not None:
        if task != "edit":
            raise ValueError("仅 edit state 可以包含源视频")
        if (not isinstance(source_windows, list) or len(source_windows) != total
                or any(not isinstance(window, list) or len(window) != 2
                       or any(isinstance(value, bool) or not isinstance(value, int)
                              or value < 0 for value in window)
                       or not _is_valid_h3_length(window[1]) or window[1] > 124
                       for window in source_windows)):
            raise ValueError("state.source_windows 非法")
        if any(scene["length"] != window[1]
               for scene, window in zip(scenes, source_windows)):
            raise ValueError("state.scenes 与源视频窗口长度不一致")
        if (not isinstance(state.get("source_24_video"), str)
                or not state["source_24_video"].strip()
                or not isinstance(state.get("source_original_video"), str)
                or not state["source_original_video"].strip()):
            raise ValueError("state.source_24_video 缺失")
    elif state.get("source_24_video") is not None or state.get("source_original_video") is not None:
        raise ValueError("非 edit state 不应包含源视频")
    if task == "edit" and source_windows is None:
        raise ValueError("edit state 缺少源视频分段")
    return state


def output_state(state: Dict[str, Any], status: str, message: str,
                 error: str = "") -> None:
    """输出由 LLM 保存并原样传回的无本地状态续跑信息"""
    result: Dict[str, Any] = {
        "success": not error,
        "status": status,
        "progress": f"{state['segments_done']}/{state['segments_total']}",
        "state": state,
        "message": message,
    }
    if error:
        result["error"] = error
    print(json.dumps(result, ensure_ascii=False))


def build_segment_workflow(seg_idx: int, state: Dict[str, Any], ffmpeg: str,
                           store: VideoStoreCore, work_dir: Path) -> Dict[str, Any]:
    """构建第 seg_idx 段工作流，所有输入均由 state 中的标识符解析"""
    scene = state["scenes"][seg_idx - 1]
    seg_length = scene["length"]
    seed = scene["seed"]
    steps = state["steps"]
    prompt = scene["prompt"]
    width, height = state["width"], state["height"]
    noise_on = state["noise"] == "on"
    task = state["task"]
    model = state["model"]
    wf_map = CHAIN_WORKFLOWS

    if seg_idx == 1:
        wf = copy.deepcopy(load_workflow(wf_map["initial"]))
        apply_prompt(wf, prompt)
        apply_length(wf, seg_length)
        apply_size(wf, width, height)
        _replace_scalar(wf, "{{seed}}", seed)
        _replace_scalar(wf, "{{steps}}", steps)
        apply_generated_audio_output(wf, continuation=False)
    else:
        wf = copy.deepcopy(load_workflow(wf_map["segment"]))
        apply_chain_params(wf, prompt, seg_length, steps, seed)
        apply_size(wf, width, height)
        # context：上一段交付尾部 22 帧 →（可选彩噪）→ 上传
        prev_delivered = _state_video_path(store, state["delivered"][-1], "delivered")
        ctx_path = work_dir / f"{state['run_id']}_ctx_{seg_idx}.mp4"
        prepare_context(ffmpeg, prev_delivered, CONTEXT_FRAMES,
                        noise_on, ctx_path, seed + seg_idx)
        ctx_name = upload_video_to_comfyui(str(ctx_path))
        wf["101"]["inputs"]["file"] = ctx_name
        wf["105"]["inputs"]["audio_vae"] = ["4", 0]
        apply_generated_audio_output(wf, continuation=True)

    # 源视频切片（角色替换模式）
    if task == "edit":
        seg_start, seg_window = state["source_windows"][seg_idx - 1]
        src_24_path = _state_video_path(store, state["source_24_video"], "source_24_video")
        slice_path = work_dir / f"{state['run_id']}_src_seg_{seg_idx}.mp4"
        slice_source_window(ffmpeg, src_24_path, seg_start, seg_window, slice_path)
        source_name = upload_video_to_comfyui(str(slice_path))
    else:
        source_name = None

    if task in ("ref", "edit"):
        apply_identity_images(wf, state["uploaded_images"])
        apply_source_video(wf, source_name)
    else:
        adapt_image_conditioning(
            wf, task, state["uploaded_images"], seg_idx,
            state["segments_total"])

    _replace_scalar(wf, "{{unet_name}}", model_checkpoint(task, model))

    # 对照实验参数必须在 task 适配后应用。
    if state.get("no_lora"):
        for node_id in ("5", "60", "70", "61"):
            wf.pop(node_id, None)
        wf["83"]["inputs"]["model"] = ["1", 0]
    # legacy_sampler 已随 turbo v4 升级移除（无 KSamplerSelect/BasicScheduler 可切）
    return wf


def submit_next_segment(state: Dict[str, Any], ffmpeg: str, store: VideoStoreCore,
                        work_dir: Path) -> None:
    """提交 state 指向的下一段，并将 ComfyUI prompt_id 写回 state"""
    seg_idx = state["segments_done"] + 1
    workflow = build_segment_workflow(seg_idx, state, ffmpeg, store, work_dir)
    state["current_prompt_id"] = submit_task(workflow)


def main() -> None:
    parser = argparse.ArgumentParser(description="MiniMax H3 链式长视频生成")
    parser.add_argument("--task", choices=TASKS, default="", help="生成模式（首次调用必填）")
    parser.add_argument("--plan-json", default="", help="逐场景 prompt/length/seed 数组")
    parser.add_argument("--images", default="", help="图片标识符，逗号分隔")
    parser.add_argument("--source-video", default="", help="edit 模式的源视频标识符")
    parser.add_argument("--model", choices=["hybrid", "official"], default="hybrid",
                        help="模型版本：hybrid=融合模型（默认），official=官方模型")
    parser.add_argument("--aspect-ratio", default="16:9", help="t2v 画幅，默认 16:9")
    parser.add_argument("--resolution", choices=list(RESOLUTION_PIXELS.keys()), default="480p")
    parser.add_argument("--noise", choices=["on", "off"], default="on")
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--no-lora", action="store_true")
    parser.add_argument("--legacy-sampler", action="store_true")
    parser.add_argument("--keep-audio", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--wait", type=int, default=240)
    parser.add_argument("--state", default="", help="LLM 上次返回的 state JSON（续跑时原样传回）")
    args = parser.parse_args()
    args.wait = min(args.wait, 540)

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        output_error("未找到 ffmpeg")
        return
    session_id = os.environ.get("SESSION_ID", "unknown")
    store = VideoStoreCore(session_id)
    state: Optional[Dict[str, Any]] = None

    try:
        with tempfile.TemporaryDirectory(prefix="h3chain_") as tmp:
            work_dir = Path(tmp)
            if args.state:
                state = _validate_state(args.state, session_id)
                prompt_id = state.get("current_prompt_id")
                if prompt_id:
                    result = poll_result(prompt_id, args.wait)
                    if result["status"] == "pending":
                        output_state(state, "partial", "当前段仍在 ComfyUI 队列中，请原样传回 state 继续查询")
                        return
                    if result["status"] == "error":
                        state["current_prompt_id"] = None
                        output_state(state, "error", "当前段生成失败，请原样传回 state 重试",
                                     result.get("error", "ComfyUI 任务失败"))
                        return
                    segment = store_video(result["data"])
                    state["delivered"].append(segment["identifier"])
                    state["segments_done"] += 1
                    state["current_prompt_id"] = None

                if state["segments_done"] >= state["segments_total"]:
                    delivered = [_state_video_path(store, ident, "delivered")
                                 for ident in state["delivered"]]
                    final_path = work_dir / "final.mp4"
                    if len(delivered) == 1:
                        shutil.copy2(delivered[0], final_path)
                    else:
                        concat_videos(ffmpeg, delivered, final_path)
                    source_id = state.get("source_original_video")
                    if state.get("keep_audio") and source_id:
                        source = _state_video_path(store, source_id, "source_original_video")
                        audio_path = work_dir / "final_audio.mp4"
                        mux_cmd = [ffmpeg, "-y", "-v", "error", "-i", str(final_path),
                                   "-i", str(source), "-map", "0:v", "-map", "1:a?",
                                   "-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart",
                                   "-shortest", str(audio_path)]
                        try:
                            run_ffmpeg(ffmpeg, mux_cmd, "音轨合成")
                        except RuntimeError:
                            fallback = mux_cmd.copy()
                            movflags_index = fallback.index("-movflags")
                            del fallback[movflags_index:movflags_index + 2]
                            try:
                                run_ffmpeg(ffmpeg, fallback, "音轨合成(无faststart)")
                            except RuntimeError as fallback_error:
                                output_error(f"音轨合成失败: {fallback_error}")
                                return
                        final_path = audio_path
                    final = store_video(final_path.read_bytes())
                    output_result(True, identifier=final["identifier"], path=final["path"],
                                  model="h3_chain")
                    return

                submit_next_segment(state, ffmpeg, store, work_dir)
                output_state(state, "partial", "下一段已提交，请原样传回 state 查询进度")
                return

            if not args.task:
                output_error("首次调用必须提供 --task")
                return
            if args.steps <= 0:
                output_error("--steps 必须是正整数")
                return
            if not 0 <= args.seed < 2 ** 64:
                output_error("--seed 必须是 uint64 整数")
                return
            if args.task == "edit" and not args.source_video.strip():
                output_error("edit 模式必须提供 --source-video")
                return
            if args.task != "edit" and args.source_video.strip():
                output_error("仅 edit 模式支持 --source-video")
                return
            if args.keep_audio and args.task != "edit":
                output_error("--keep-audio 仅用于 edit 模式")
                return

            scenes = _parse_plan(args.plan_json)
            if any(index > 0 and scene["length"] < CONTEXT_FRAMES + H3_MIN_FRAMES
                   for index, scene in enumerate(scenes)):
                output_error("续写场景至少需要 39 帧（含 22 帧上下文）")
                return

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
            required_images = {"t2v": 0, "i2v": 1, "fl2v": 2}
            if args.task in required_images and len(image_paths) != required_images[args.task]:
                output_error(f"{args.task} 模式需要 {required_images[args.task]} 张图片")
                return
            if args.task in ("ref", "edit") and not 1 <= len(image_paths) <= 4:
                output_error(f"{args.task} 模式需要 1-4 张参考图")
                return

            if args.task == "t2v":
                width, height = compute_size_for_aspect(
                    args.aspect_ratio, max_pixels=RESOLUTION_PIXELS[args.resolution])
            else:
                width, height = compute_target_size(
                    image_paths[0], max_pixels=RESOLUTION_PIXELS[args.resolution])
            run_id = uuid.uuid4().hex[:12]
            uploaded_images = []
            for i, image_path in enumerate(image_paths, 1):
                upload_path = work_dir / f"{run_id}_card_{i}{Path(image_path).suffix}"
                shutil.copy2(image_path, upload_path)
                uploaded_images.append(upload_image_to_comfyui(str(upload_path)))

            base_seed = args.seed if args.seed else random.getrandbits(63)
            for index, scene in enumerate(scenes):
                if scene["seed"] is None:
                    scene["seed"] = (base_seed + index) % (2 ** 64)

            initial_state: Dict[str, Any] = {
                "version": STATE_VERSION,
                "task": args.task,
                "run_id": run_id,
                "session_id": session_id,
                "scenes": scenes,
                "segments_total": len(scenes),
                "segments_done": 0,
                "current_prompt_id": None,
                "delivered": [],
                "width": width,
                "height": height,
                "steps": args.steps,
                "noise": args.noise,
                "model": args.model,
                "no_lora": args.no_lora,
                "legacy_sampler": args.legacy_sampler,
                "keep_audio": args.keep_audio,
                "uploaded_images": uploaded_images,
                "source_windows": None,
                "source_24_video": None,
                "source_original_video": None,
            }

            if args.task == "edit":
                source_id = args.source_video.strip()
                source_path = _state_video_path(store, source_id, "source_video")
                initial_state["source_original_video"] = source_id
                src_24_path = work_dir / f"{run_id}_src_24fps.mp4"
                convert_to_24fps(ffmpeg, source_path, src_24_path)
                sw, sh = probe_video_size(ffmpeg, src_24_path)
                initial_state["width"], initial_state["height"] = compute_target_size_wh(
                    sw, sh, RESOLUTION_PIXELS[args.resolution])
                windows = plan_source_windows(count_frames(ffmpeg, src_24_path))
                if len(windows) > len(scenes):
                    windows = windows[:len(scenes)]
                if not windows:
                    output_error("源视频长度不足以生成有效分段")
                    return
                initial_state["source_windows"] = windows
                initial_state["segments_total"] = len(windows)
                initial_state["scenes"] = scenes[:len(windows)]
                for scene, (_, window) in zip(initial_state["scenes"], windows):
                    scene["length"] = window
                initial_state["source_24_video"] = store_video(
                    src_24_path.read_bytes())["identifier"]

            state = initial_state
            submit_next_segment(state, ffmpeg, store, work_dir)
            output_state(state, "partial", "第 1 段已提交，请原样传回 state 查询进度")
    except (RuntimeError, ValueError, OSError) as e:
        if state is not None:
            output_state(state, "error", "链式任务未完成，请原样传回 state 重试", str(e))
        else:
            output_error(str(e))


def main_with_args(argv: list) -> None:
    """带参数入口（供外部 runner 复用）"""
    sys.argv = ["comfyui_video_chain.py"] + argv
    main()


if __name__ == "__main__":
    main()
