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
import shutil
import subprocess
import sys
import tempfile
import time
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
    load_workflow, apply_prompt, apply_input_images,
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
    """按宽高比计算目标分辨率（32 对齐，像素量不超 max_pixels）"""
    aspect = width / height
    scale = min((max_pixels / (width * height)) ** 0.5, 1.0)
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
            if window < H3_MIN_FRAMES:
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


# ---------- 链式任务状态机（execute_script 300s 超时下分阶段续跑） ----------

# 任务状态标记
STALE_MAX_HOURS = 24.0   # 死任务清理阈值
MAX_FAIL_COUNT = 3       # 同任务连续失败上限（超出标记 failed）

def _state_root() -> Path:
    """状态根目录：data/aichat/chain_state/{session_id}/{key}/"""
    project = Path(os.environ.get("PROJECT_ROOT", ".")).resolve()
    session_id = os.environ.get("SESSION_ID", "unknown")
    return project / "data" / "aichat" / "chain_state" / session_id


def new_state_key() -> str:
    """生成唯一任务 key"""
    import uuid
    return time.strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6]


def save_state(state: Dict[str, Any]) -> None:
    """保存任务状态（原子写：先写临时文件再改名）"""
    state["updated_at"] = time.time()
    state_dir = Path(state["state_dir"])
    state_dir.mkdir(parents=True, exist_ok=True)
    tmp = state_dir / "state.json.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.rename(state_dir / "state.json")


def load_state(key: str) -> Optional[Dict[str, Any]]:
    """按 key 加载任务状态"""
    state_file = _state_root() / key / "state.json"
    if not state_file.exists():
        return None
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return None


LOCK_MAX_AGE = 360  # 锁最长持有秒数（正常 resume ≤270s；超 360 必为死锁残留，自动清理）


def _acquire_lock(state_dir: Path) -> bool:
    """获取任务目录锁（O_EXCL 原子创建 + 时间戳死锁检测）

    进程被 execute_script 超时杀掉（SIGKILL）时 finally 不执行，锁会残留；
    持有超 LOCK_MAX_AGE 的锁视为死锁，自动清理后重取。
    """
    lock = state_dir / ".lock"

    def try_create() -> bool:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(int(time.time())).encode())
            os.close(fd)
            return True
        except FileExistsError:
            return False

    if try_create():
        return True
    # 已存在：死锁检测
    try:
        age = time.time() - float(lock.read_text().strip())
    except Exception:
        age = time.time()  # 无有效时间戳的旧锁视为死锁
    if age > LOCK_MAX_AGE:
        try:
            lock.unlink()
        except OSError:
            pass
        return try_create()
    return False


def _release_lock(state_dir: Path) -> None:
    lock = state_dir / ".lock"
    try:
        lock.unlink()
    except OSError:
        pass


def cleanup_stale(max_age_hours: float = STALE_MAX_HOURS) -> None:
    """清理过期/失败/损坏的任务状态（每次 main 启动时调用）"""
    root = _state_root()
    if not root.exists():
        return
    now = time.time()
    for key in list(root.iterdir()):
        state_file = root / key / "state.json"
        if not state_file.exists():
            shutil.rmtree(root / key, ignore_errors=True)
            continue
        try:
            st = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            shutil.rmtree(root / key, ignore_errors=True)
            continue
        if st.get("status") == "failed":
            shutil.rmtree(root / key, ignore_errors=True)
        elif now - st.get("updated_at", 0) > max_age_hours * 3600:
            shutil.rmtree(root / key, ignore_errors=True)


def find_active_task() -> Optional[str]:
    """查找会话内活跃任务 key（running 且未过期，取最新更新的）"""
    root = _state_root()
    if not root.exists():
        return None
    now = time.time()
    best: Optional[tuple] = None
    for key in root.iterdir():
        state_file = root / key / "state.json"
        if not state_file.exists():
            continue
        try:
            st = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if st.get("status") == "failed":
            continue
        if now - st.get("updated_at", 0) > STALE_MAX_HOURS * 3600:
            continue
        if st.get("segments_done", 0) < st.get("segments_total", 0):
            if best is None or st.get("updated_at", 0) > best[1]:
                best = (key.name, st.get("updated_at", 0))
    return best[0] if best else None


def output_partial(state: Dict[str, Any]) -> None:
    """输出分阶段进度（LLM 据此继续调用 --resume）"""
    print(json.dumps({
        "success": True,
        "status": "partial",
        "progress": f"{state['segments_done']}/{state['segments_total']}",
        "resume_key": state["key"],
        "message": f"链式生成进行中（{state['segments_done']}/{state['segments_total']} 段完成），"
                   f"继续调用 --resume {state['key']}",
    }, ensure_ascii=False))


def output_resumable_error(state: Optional[Dict[str, Any]], error: str) -> None:
    """输出可恢复错误（保留状态，可 --resume 重试）"""
    if state:
        print(json.dumps({
            "success": False,
            "error": error,
            "resume_key": state["key"],
            "message": f"可用 --resume {state['key']} 重试",
        }, ensure_ascii=False))
    else:
        output_error(error)


def build_segment_workflow(seg_idx: int, state: Dict[str, Any], ffmpeg: str) -> Dict[str, Any]:
    """构建第 seg_idx 段的工作流（从状态恢复所有中间产物）"""
    seg_length = state["seg_lengths"][seg_idx - 1]
    seed = state["seed"]
    steps = state["steps"]
    prompt = state["prompt"]
    width, height = state["width"], state["height"]
    noise_on = state["noise"] == "on"
    state_dir = Path(state["state_dir"])

    if seg_idx == 1:
        wf = copy.deepcopy(load_workflow(CHAIN_WORKFLOWS["initial"]))
        apply_prompt(wf, prompt)
        apply_length(wf, seg_length)
        apply_size(wf, width, height)
        _replace_scalar(wf, "{{seed}}", seed)
        _replace_scalar(wf, "{{steps}}", steps)
    else:
        wf = copy.deepcopy(load_workflow(CHAIN_WORKFLOWS["segment"]))
        apply_chain_params(wf, prompt, seg_length, steps, seed)
        apply_size(wf, width, height)
        # context：上一段交付尾部 22 帧 →（可选彩噪）→ 上传
        prev_delivered = Path(state["delivered"][-1])
        ctx_path = state_dir / f"{state['key']}_ctx_{seg_idx}.mp4"
        prepare_context(ffmpeg, prev_delivered, CONTEXT_FRAMES,
                        noise_on, ctx_path, seed + seg_idx)
        ctx_name = upload_video_to_comfyui(str(ctx_path))
        state["ctx_names"][str(seg_idx)] = ctx_name
        wf["101"]["inputs"]["file"] = ctx_name

    # 源视频切片（角色替换模式）
    if state.get("source_windows"):
        seg_start, seg_window = state["source_windows"][seg_idx - 1]
        # 本地文件名带任务 key 前缀：并发任务上传到 ComfyUI input 时避免同名冲突
        slice_path = state_dir / f"{state['key']}_src_seg_{seg_idx}.mp4"
        slice_source_window(ffmpeg, Path(state["src_24_path"]), seg_start, seg_window, slice_path)
        source_name = upload_video_to_comfyui(str(slice_path))
        state["seg_slice_names"][str(seg_idx)] = source_name
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


def run_segment(seg_idx: int, state: Dict[str, Any], ffmpeg: str, wait: int) -> str:
    """执行第 seg_idx 段：提交（如需）→ 轮询 → 存交付文件

    Returns: "done" / "pending" / "error"
    """
    state["current_seg"] = seg_idx
    prompt_id = state.get("current_prompt_id")
    if not prompt_id:
        wf = build_segment_workflow(seg_idx, state, ffmpeg)
        prompt_id = submit_task(wf)
        state["current_prompt_id"] = prompt_id
        save_state(state)

    result = poll_result(prompt_id, wait)
    if result["status"] == "done":
        state_dir = Path(state["state_dir"])
        seg_file = state_dir / f"seg_{seg_idx}.mp4"
        seg_file.write_bytes(result["data"])
        state["delivered"].append(str(seg_file))
        state["segments_done"] = seg_idx
        state["current_prompt_id"] = None
        state["fail_count"] = 0  # 段成功重置失败计数
        save_state(state)
        return "done"
    if result["status"] == "pending":
        save_state(state)
        return "pending"
    # error：记录失败次数，超限标记 failed（防 resume 死循环）；状态保留可重试
    state["current_prompt_id"] = None
    state["fail_count"] = state.get("fail_count", 0) + 1
    if state["fail_count"] >= MAX_FAIL_COUNT:
        state["status"] = "failed"
    save_state(state)
    return "error"


def main() -> None:
    parser = argparse.ArgumentParser(description="MiniMax H3 链式长视频生成")
    parser.add_argument("--images", default="", help="身份参考图标识符，逗号分隔（1-4 张，作 <Picture N>）")
    parser.add_argument("--source-video", default="", help="源视频标识符（可选，作 <Video 1> 角色替换）")
    parser.add_argument("--prompt", default="", help="六段式提示词（含 <Picture N> / <Video 1> 引用）")
    parser.add_argument("--segments", type=int, default=2, help="总段数（默认 2；每段约 1-3 分钟）")
    parser.add_argument("--duration", type=float, default=5.0, help="每段时长（秒，建议 >=5，默认 5；仅纯续写模式有效）")
    parser.add_argument("--resolution", choices=list(RESOLUTION_PIXELS.keys()), default="480p",
                        help="分辨率档位（默认 480p；768p 高清约 3-5 倍耗时）")
    parser.add_argument("--noise", choices=["on", "off"], default="on",
                        help="彩噪 taper 注入（默认 on：防链式锐度衰减；off 关闭）")
    parser.add_argument("--steps", type=int, default=4, help="每段采样步数（默认 4，ref2v turbo LoRA 配置；质量优先可调 8/20）")
    parser.add_argument("--no-lora", action="store_true",
                        help="不使用 ref2v turbo LoRA/SigmaShift（工作流直连 UNET，供对照实验）")
    parser.add_argument("--legacy-sampler", action="store_true",
                        help="恢复旧采样器 res_multistep/beta（v5 时代配置，供对照实验）")
    parser.add_argument("--keep-audio", action="store_true",
                        help="成片保留源视频音轨（mux 原片 BGM/对白，时间轴 1:1 对齐）")
    parser.add_argument("--seed", type=int, default=0, help="随机种子（0=随机）")
    parser.add_argument("--wait", type=int, default=280, help="每段等待秒数（默认 280，自动 clamp 到 240 保证单次调用 <300s）")
    parser.add_argument("--resume", default="", help="续跑已有任务（key 来自上次 partial 返回）")
    args = parser.parse_args()

    # 单次调用预算：poll 240s + 提交下一段 ~30s = 270s < execute_script 300s 硬上限
    args.wait = min(args.wait, 240)

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        output_error("未找到 ffmpeg")
        return

    # 启动时清理过期/失败/损坏的残留任务状态
    cleanup_stale()

    lock_dir: Optional[Path] = None  # resume 分支获取的锁，退出前释放

    # ================= 续跑分支 =================
    if args.resume:
        state = load_state(args.resume.strip())
        if not state:
            output_error(f"任务不存在或状态已清理: {args.resume}")
            return
        session_id = os.environ.get("SESSION_ID", "unknown")
        if state.get("session_id") != session_id:
            output_error("任务不属于当前会话，无法续跑")
            return
        if state.get("status") == "failed":
            output_error(f"任务 {args.resume} 已标记失败（连续失败超限或状态损坏），请重新发起任务")
            return
        # 防并发：独占锁（另一个 resume 进程正在处理时拒绝）
        if not _acquire_lock(Path(state["state_dir"])):
            output_error(f"任务 {args.resume} 正在被其他调用处理，请稍后重试")
            return
        lock_dir = Path(state["state_dir"])
    else:
        # ================= 首次提交分支 =================
        # 会话级互斥：已有活跃任务时拒绝新建，提示 resume 旧任务
        active_key = find_active_task()
        if active_key:
            output_error(f"会话已有进行中的链式任务，请使用 --resume {active_key} 继续（不要重复发起新任务）")
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

        # ---- 身份参考图解析 + 上传 ----
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
        if len(image_paths) > 4:
            output_error("身份参考图最多 4 张")
            return
        try:
            width, height = compute_target_size(image_paths[0], max_pixels=RESOLUTION_PIXELS[args.resolution])
        except Exception as e:
            output_error(f"图片尺寸计算失败: {e}")
            return

        # ---- 初始化任务状态 ----
        key = new_state_key()
        state_dir = _state_root() / key
        state_dir.mkdir(parents=True, exist_ok=True)

        # ---- 身份参考图上传（上传名唯一化：ComfyUI 同名上传会覆盖） ----
        try:
            uploaded_images = []
            for i, p in enumerate(image_paths):
                card_path = state_dir / f"{key}_card_{i + 1}{Path(p).suffix}"
                shutil.copy2(p, card_path)
                uploaded_images.append(upload_image_to_comfyui(str(card_path)))
        except Exception as e:
            output_error(f"图片上传失败: {e}")
            return
        state: Dict[str, Any] = {
            "key": key,
            "session_id": os.environ.get("SESSION_ID", "unknown"),
            "created_at": time.time(),
            "updated_at": time.time(),
            "status": "running",
            "fail_count": 0,
            "state_dir": str(state_dir),
            "prompt": args.prompt,
            "segments_total": args.segments,
            "segments_done": 0,
            "current_seg": 0,
            "current_prompt_id": None,
            "delivered": [],
            "width": width,
            "height": height,
            "seed": args.seed if args.seed else random.getrandbits(63),
            "steps": args.steps,
            "noise": args.noise,
            "no_lora": args.no_lora,
            "legacy_sampler": args.legacy_sampler,
            "keep_audio": args.keep_audio,
            "uploaded_images": uploaded_images,
            "seg_lengths": [],
            "source_windows": None,
            "src_24_path": None,
            "src_original_path": None,
            "seg_slice_names": {},
            "ctx_names": {},
        }

        # ---- 源视频预处理（可选） ----
        if args.source_video:
            store = VideoStoreCore(state["session_id"])
            src_path = store.get_file_path(args.source_video.strip())
            if not src_path or not Path(src_path).exists():
                output_error(f"源视频不存在: {args.source_video}")
                return
            state["src_original_path"] = str(Path(src_path))
            try:
                src_24_path = state_dir / "src_24fps.mp4"
                convert_to_24fps(ffmpeg, src_path, src_24_path)
                sw, sh = probe_video_size(ffmpeg, src_24_path)
                width, height = compute_target_size_wh(sw, sh, RESOLUTION_PIXELS[args.resolution])
                state["width"], state["height"] = width, height
                state["src_24_path"] = str(src_24_path)
                state["source_windows"] = plan_source_windows(count_frames(ffmpeg, src_24_path))
                if len(state["source_windows"]) > args.segments:
                    state["source_windows"] = state["source_windows"][:args.segments]
                state["segments_total"] = len(state["source_windows"])
            except Exception as e:
                output_error(f"源视频预处理失败: {e}")
                return
            for _, w in state["source_windows"]:
                state["seg_lengths"].append(w)
        else:
            length = duration_to_frames(args.duration)
            state["seg_lengths"] = [length] * args.segments
        save_state(state)

        # 首次调用：提交段 1 后立即返回 partial（不等待）
        # 原因：execute_script 有 300s 硬超时，预处理+提交段1 可能已占 40s，
        # 若再 poll 280s 会超时被杀，partial/resume_key 丢失（LLM 拿不到 key）。
        # 所有等待放到后续 --resume 调用。
        try:
            wf = build_segment_workflow(1, state, ffmpeg)
            prompt_id = submit_task(wf)
        except RuntimeError as e:
            output_resumable_error(state, f"段 1 提交失败: {e}")
            return
        state["current_prompt_id"] = prompt_id
        state["current_seg"] = 1
        save_state(state)
        output_partial(state)
        return

    # ================= 通用执行循环（首次/续跑共用） =================
    # 时间预算：单次调用必须在 execute_script 300s 硬上限内正常退出。
    # 预算 = poll(wait) + 提交下一段余量(30s)；预算将尽时主动返回 partial
    # （正常退出、释放锁），不等到被超时杀进程（SIGKILL 会残留锁/丢输出）。
    call_deadline = time.time() + args.wait + 30
    try:
        while state["segments_done"] < state["segments_total"]:
            if time.time() > call_deadline:
                if lock_dir:
                    _release_lock(lock_dir)
                output_partial(state)
                return
            seg_idx = state["segments_done"] + 1
            result = run_segment(seg_idx, state, ffmpeg, args.wait)
            if result == "done":
                continue
            if result == "pending":
                if lock_dir:
                    _release_lock(lock_dir)
                output_partial(state)
                return
            # error：可恢复（状态保留）
            if lock_dir:
                _release_lock(lock_dir)
            output_resumable_error(state, f"第 {seg_idx} 段生成失败")
            return

        # ---- 全部段完成：交付文件校验 → 拼接 + 可选音轨 + 交付 ----
        delivered = [Path(p) for p in state["delivered"]]
        missing = [str(p) for p in delivered
                   if not p.exists() or p.stat().st_size == 0]
        if missing:
            state["status"] = "failed"
            save_state(state)
            output_resumable_error(state, f"交付文件缺失，任务状态损坏: {missing}")
            return
        state_dir = Path(state["state_dir"])
        final_path = state_dir / "final.mp4"
        if len(delivered) == 1:
            shutil.copy2(delivered[0], final_path)
        else:
            concat_videos(ffmpeg, delivered, final_path)

        if state.get("keep_audio") and state.get("src_original_path"):
            src_original = Path(state["src_original_path"])
            if src_original.exists():
                audio_path = state_dir / "final_audio.mp4"
                run_ffmpeg(ffmpeg, [
                    ffmpeg, "-y", "-v", "error",
                    "-i", str(final_path), "-i", str(src_original),
                    "-map", "0:v", "-map", "1:a?",
                    "-c:v", "copy", "-c:a", "aac",
                    "-movflags", "+faststart", "-shortest",
                    str(audio_path),
                ], "音轨合成")
                final_path = audio_path

        stored = store_video(final_path.read_bytes())
        # 交付成功：清理状态（锁文件随目录一并删除）
        shutil.rmtree(state_dir, ignore_errors=True)
        lock_dir = None
        output_result(True, identifier=stored["identifier"], path=stored["path"],
                      model="h3_chain")
    except Exception as e:
        # 异常：保留状态，可续跑
        if lock_dir:
            _release_lock(lock_dir)
        output_resumable_error(state, f"链式生成异常: {e}")


def main_with_args(argv: list) -> None:
    """带参数入口（供外部 runner 复用）"""
    sys.argv = ["comfyui_video_chain.py"] + argv
    main()


if __name__ == "__main__":
    main()
