#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-08-23
Description: MiniMax H3 链式长视频生成（Motion Context 续写），供 video_generation SKILL 调用

原理（参考 MacroSony/minimax-h3-chained-character-swap）：
- 段 1 用 h3_chain_initial（无上下文），后续段用 h3_chain_segment
- 每段以上一段交付视频的尾部 22 帧为 Motion Context（ChainContext 编码为
  latent token 钉在下一段时间轴头部），raw 输出前 22 帧为 context 复刻，
  由工作流内 LoopTrim 裁除，交付段可直接拼接
- 彩噪 taper 注入（--noise on，默认）：context 前 19 帧 @0.45 注噪 +
  末 3 帧渐弱到 0.10，触发模型修复模式，防链式锐度衰减（实测 +8-9%）
- 无源视频时（纯续写）移除 ref_videos 引用；角色替换时源视频作 <Video 1>
- 各段无音轨（链式音频不连续），成片可用 assemble.py 统一加 BGM

约定：
- 身份参考图: --images（1-4 张，作 <Picture N>）
- 源视频: --source-video（可选，作 <Video 1>）
- 每段时长: --duration（秒，建议 >=5，默认 5）
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
    COMFYUI_BASE_URL, RESOLUTION_PIXELS, VideoStoreCore, H3_MIN_FRAMES,
    duration_to_frames, compute_target_size,
    upload_image_to_comfyui, submit_task, poll_result,
    store_video, apply_length, apply_size, http_post,
)

# 链式工作流文件名（reference/ 下）
CHAIN_WORKFLOWS = {
    "initial": "h3_chain_initial",   # 段 1：无 context
    "segment": "h3_chain_segment",   # 续写段：22 帧 Motion Context + LoopTrim
}

# 融合模型版（fl2va 基座 + ref2va 后段 adaln_proj）
CHAIN_WORKFLOWS_HYBRID = {
    "initial": "h3_chain_initial_hybrid",
    "segment": "h3_chain_segment_hybrid",
}

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
    """探测 ffmpeg：imageio_ffmpeg → 系统 → ComfyUI venv 二进制"""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except ImportError:
        pass
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    for candidate in sorted(Path("/root/bot/comfyui/.venv").glob("lib/*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*")):
        return str(candidate)
    return None


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
    """从交付视频提取尾部 tail 帧，可选彩噪 taper 注入，重编码 24fps 输出

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

        # 重命名连续序号后重编码（24fps，无音轨）
        keep_dir = tmp / "keep"
        keep_dir.mkdir()
        for i, f in enumerate(keep, 1):
            shutil.copy2(f, keep_dir / f"k_{i:04d}.png")
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-framerate", str(FRAME_RATE),
             "-i", str(keep_dir / "k_%04d.png"),
             "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", "-an",
             str(out_path)],
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


def concat_videos(ffmpeg: str, paths: List[Path], out_path: Path) -> None:
    """ffmpeg concat 拼接（统一重编码保证编码器一致）"""
    list_file = out_path.parent / "concat.txt"
    list_file.write_text("".join(f"file '{p}'\n" for p in paths), encoding="utf-8")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
             "-c:v", "libx264", "-preset", "fast", "-crf", "20",
             "-movflags", "+faststart", str(out_path)],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        detail = e.stderr.decode("utf-8", "replace")[-400:] if e.stderr else ""
        raise RuntimeError(f"拼接失败(exit {e.returncode}): {detail}")


# ---------- 无本地状态续跑 ----------

STATE_VERSION = 1
RUN_ID_RE = re.compile(r"^[0-9a-f]{12}$")


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
    if not isinstance(total, int) or not isinstance(done, int) or not 0 <= done <= total:
        raise ValueError("state 分段进度非法")
    if not isinstance(state.get("segment_lengths"), list) or len(state["segment_lengths"]) != total:
        raise ValueError("state.segment_lengths 非法")
    if not isinstance(state.get("delivered"), list) or len(state["delivered"]) != done:
        raise ValueError("state.delivered 与进度不一致")
    prompt_id = state.get("current_prompt_id")
    if prompt_id is not None and not isinstance(prompt_id, str):
        raise ValueError("state.current_prompt_id 非法")
    if done == total and prompt_id is not None:
        raise ValueError("已完成任务不能保留 current_prompt_id")
    if not isinstance(state.get("uploaded_images"), list) or not state["uploaded_images"]:
        raise ValueError("state.uploaded_images 非法")
    if state.get("source_windows") is not None:
        if not isinstance(state.get("source_24_video"), str):
            raise ValueError("state.source_24_video 缺失")
        if len(state["source_windows"]) != total:
            raise ValueError("state.source_windows 与分段数不一致")
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
    seg_length = state["segment_lengths"][seg_idx - 1]
    seed = state["seed"]
    steps = state["steps"]
    prompt = state["prompt"]
    width, height = state["width"], state["height"]
    noise_on = state["noise"] == "on"
    # 模型版本写入 state，续跑段间保持一致；老 state 无该字段时默认 hybrid
    wf_map = CHAIN_WORKFLOWS_HYBRID if state.get("model", "hybrid") == "hybrid" else CHAIN_WORKFLOWS

    if seg_idx == 1:
        wf = copy.deepcopy(load_workflow(wf_map["initial"]))
        apply_prompt(wf, prompt)
        apply_length(wf, seg_length)
        apply_size(wf, width, height)
        _replace_scalar(wf, "{{seed}}", seed)
        _replace_scalar(wf, "{{steps}}", steps)
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

    # 源视频切片（角色替换模式）
    if state.get("source_windows"):
        seg_start, seg_window = state["source_windows"][seg_idx - 1]
        src_24_path = _state_video_path(store, state["source_24_video"], "source_24_video")
        slice_path = work_dir / f"{state['run_id']}_src_seg_{seg_idx}.mp4"
        slice_source_window(ffmpeg, src_24_path, seg_start, seg_window, slice_path)
        source_name = upload_video_to_comfyui(str(slice_path))
    else:
        source_name = None

    # 对照实验参数
    if state.get("no_lora"):
        wf.pop("60", None)
        wf.pop("61", None)
        wf["15"]["inputs"]["model"] = ["1", 0]
    if state.get("legacy_sampler"):
        wf["13"]["inputs"]["sampler_name"] = "res_multistep"
        wf["14"]["inputs"]["scheduler"] = "beta"

    apply_identity_images(wf, state["uploaded_images"])
    apply_source_video(wf, source_name)
    return wf


def submit_next_segment(state: Dict[str, Any], ffmpeg: str, store: VideoStoreCore,
                        work_dir: Path) -> None:
    """提交 state 指向的下一段，并将 ComfyUI prompt_id 写回 state"""
    seg_idx = state["segments_done"] + 1
    workflow = build_segment_workflow(seg_idx, state, ffmpeg, store, work_dir)
    state["current_prompt_id"] = submit_task(workflow)


def main() -> None:
    parser = argparse.ArgumentParser(description="MiniMax H3 链式长视频生成")
    parser.add_argument("--images", default="", help="身份参考图标识符，逗号分隔（1-4 张，作 <Picture N>）")
    parser.add_argument("--source-video", default="", help="源视频标识符（可选，作 <Video 1> 角色替换）")
    parser.add_argument("--model", choices=["hybrid", "official"], default="hybrid",
                        help="模型版本：hybrid=融合模型（默认），official=官方 ref2va")
    parser.add_argument("--prompt", default="", help="六段式提示词（含 <Picture N> / <Video 1> 引用）")
    parser.add_argument("--segments", type=int, default=2, help="总段数（默认 2）")
    parser.add_argument("--duration", type=float, default=5.0, help="每段时长（秒，仅纯续写模式有效）")
    parser.add_argument("--resolution", choices=list(RESOLUTION_PIXELS.keys()), default="480p")
    parser.add_argument("--noise", choices=["on", "off"], default="on")
    parser.add_argument("--steps", type=int, default=4)
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
                    final = store_video(final_path.read_bytes())
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
                            final = store_video(audio_path.read_bytes())
                        except RuntimeError:
                            fallback = [item for item in mux_cmd if item != "+faststart"]
                            try:
                                run_ffmpeg(ffmpeg, fallback, "音轨合成(无faststart)")
                                final = store_video(audio_path.read_bytes())
                            except RuntimeError:
                                pass
                    output_result(True, identifier=final["identifier"], path=final["path"],
                                  model="h3_chain")
                    return

                submit_next_segment(state, ffmpeg, store, work_dir)
                output_state(state, "partial", "下一段已提交，请原样传回 state 查询进度")
                return

            if not args.prompt:
                output_error("--prompt 参数必填")
                return
            if not args.images:
                output_error("需要提供 --images 身份参考图标识符")
                return
            if not 1 <= args.segments <= 10:
                output_error("--segments 仅支持 1-10 段")
                return
            if not 1.0 <= args.duration <= 15.0:
                output_error("每段时长仅支持 1-15 秒")
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
            if not 1 <= len(image_paths) <= 4:
                output_error("身份参考图需要 1-4 张")
                return

            width, height = compute_target_size(image_paths[0],
                                                max_pixels=RESOLUTION_PIXELS[args.resolution])
            run_id = uuid.uuid4().hex[:12]
            uploaded_images = []
            for i, image_path in enumerate(image_paths, 1):
                upload_path = work_dir / f"{run_id}_card_{i}{Path(image_path).suffix}"
                shutil.copy2(image_path, upload_path)
                uploaded_images.append(upload_image_to_comfyui(str(upload_path)))

            state = {
                "version": STATE_VERSION,
                "run_id": run_id,
                "session_id": session_id,
                "prompt": args.prompt,
                "segments_total": args.segments,
                "segments_done": 0,
                "current_prompt_id": None,
                "delivered": [],
                "width": width,
                "height": height,
                "seed": args.seed if args.seed else random.getrandbits(63),
                "steps": args.steps,
                "noise": args.noise,
                "model": args.model,
                "no_lora": args.no_lora,
                "legacy_sampler": args.legacy_sampler,
                "keep_audio": args.keep_audio,
                "uploaded_images": uploaded_images,
                "segment_lengths": [],
                "source_windows": None,
                "source_24_video": None,
                "source_original_video": None,
            }

            if args.source_video:
                source_id = args.source_video.strip()
                source_path = _state_video_path(store, source_id, "source_video")
                state["source_original_video"] = source_id
                src_24_path = work_dir / f"{run_id}_src_24fps.mp4"
                convert_to_24fps(ffmpeg, source_path, src_24_path)
                sw, sh = probe_video_size(ffmpeg, src_24_path)
                state["width"], state["height"] = compute_target_size_wh(
                    sw, sh, RESOLUTION_PIXELS[args.resolution])
                windows = plan_source_windows(count_frames(ffmpeg, src_24_path))
                if len(windows) > args.segments:
                    windows = windows[:args.segments]
                if not windows:
                    output_error("源视频长度不足以生成有效分段")
                    return
                state["source_windows"] = windows
                state["segments_total"] = len(windows)
                state["segment_lengths"] = [window for _, window in windows]
                state["source_24_video"] = store_video(src_24_path.read_bytes())["identifier"]
            else:
                length = duration_to_frames(args.duration)
                if args.segments > 1 and length < CONTEXT_FRAMES + H3_MIN_FRAMES:
                    output_error("多段纯续写每段至少需要 39 帧（约 1.6 秒）")
                    return
                state["segment_lengths"] = [length] * args.segments

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
