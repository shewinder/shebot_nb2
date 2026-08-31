#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-08-28
Description: 视频超分（RealESRGAN anime_6B，2x），供 video_generation SKILL 使用

超分任务按 24 帧分块提交 ComfyUI。每次调用只等待一个块，LLM 将返回的
state 原样传回即可继续；中间文件固定保存在当前会话的 tmp 目录，只有全部
分块完成后才写入 VideoStore。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
_IG_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "image_generation" / "scripts"
sys.path.insert(0, str(_IG_SCRIPTS))

from comfyui_video import poll_result, submit_task  # noqa: E402
from comfyui_video_chain import upload_video_to_comfyui  # noqa: E402
from _common import output_error, output_result  # noqa: E402

# 视频存储核心（与会话绑定）
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

CHUNK_FRAMES = 24
FRAME_RATE = 24
STATE_VERSION = 1
STATE_KIND = "video_upscale"
RUN_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def find_ffmpeg() -> str:
    """定位 ffmpeg：优先 ComfyUI venv 的 imageio-ffmpeg，其次 PATH。"""
    candidates: List[str] = []
    comfyui_venv = Path("/root/bot/comfyui/.venv")
    if comfyui_venv.exists():
        for site_packages in sorted((comfyui_venv / "lib").glob("*/site-packages")):
            bins = sorted((site_packages / "imageio_ffmpeg" / "binaries").glob("ffmpeg-*"))
            if bins:
                candidates.append(str(bins[0]))
    which = shutil.which("ffmpeg")
    if which:
        candidates.append(which)
    if not candidates:
        raise RuntimeError("未找到 ffmpeg（ComfyUI venv 与 PATH 均无）")
    return candidates[0]


def build_upscale_workflow(fname: str, width: int, height: int, prefix: str) -> dict:
    """构建单块超分工作流。"""
    return {
        "1": {"class_type": "LoadVideo", "inputs": {"file": fname}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "3": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "RealESRGAN_x4plus_anime_6B.pth"}},
        "4": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["3", 0], "image": ["2", 0]}},
        "5": {"class_type": "ImageScale", "inputs": {
            "image": ["4", 0], "upscale_method": "lanczos",
            "width": width, "height": height, "crop": "disabled"}},
        "6": {"class_type": "CreateVideo", "inputs": {"images": ["5", 0], "fps": float(FRAME_RATE), "bit_depth": 8}},
        "7": {"class_type": "SaveVideo", "inputs": {"video": ["6", 0],
              "filename_prefix": prefix, "format": "mp4", "codec": "auto"}},
    }


def _session_tmp_dir() -> Path:
    """返回当前会话临时目录；续跑不依赖 tempfile 的随机目录。"""
    configured = os.environ.get("SESSION_TMP_DIR")
    if configured:
        return Path(configured).resolve()
    session_dir = os.environ.get("AICHAT_SESSION_DIR") or os.environ.get("SESSION_DIR")
    if session_dir:
        return (Path(session_dir).resolve() / "tmp")
    session_id = os.environ.get("SESSION_ID", "unknown")
    return (Path(os.environ.get("PROJECT_ROOT", ".")).resolve()
            / "data" / "aichat" / "sessions" / session_id / "tmp")


def _run_dir(run_id: str) -> Path:
    """根据安全的 run_id 构造会话内工作目录。"""
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id 非法")
    return _session_tmp_dir() / f"upscale_{run_id}"


def _state_video_path(store: Any, identifier: Any, field: str) -> Path:
    """从当前会话 VideoStore 解析 state 中的视频标识符。"""
    if not isinstance(identifier, str):
        raise ValueError(f"state.{field} 必须是视频标识符")
    path = store.get_file_path(identifier)
    if not path:
        raise ValueError(f"state.{field} 对应的视频不存在或不属于当前会话")
    return path


def _validate_state(raw: str, session_id: str) -> Dict[str, Any]:
    """校验 LLM 原样回传的超分 state。"""
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"--state 不是有效 JSON: {e.msg}")
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        raise ValueError("--state 版本不支持")
    if state.get("kind") != STATE_KIND:
        raise ValueError("--state 类型不支持")
    if state.get("session_id") != session_id:
        raise ValueError("state 不属于当前会话")
    run_id = state.get("run_id")
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("state.run_id 非法")
    if not isinstance(state.get("source_video"), str) or not state["source_video"].strip():
        raise ValueError("state.source_video 非法")
    if state.get("scale") not in (2, 4):
        raise ValueError("state.scale 非法")
    for key in ("chunk_frames", "source_fps", "source_width", "source_height", "total_frames", "chunks_total", "chunks_done", "current_chunk"):
        if not isinstance(state.get(key), int):
            raise ValueError(f"state.{key} 非法")
    if state["chunk_frames"] != CHUNK_FRAMES or state["source_fps"] != FRAME_RATE:
        raise ValueError("state 视频参数不受支持")
    if state["source_width"] <= 0 or state["source_height"] <= 0 or state["total_frames"] <= 0:
        raise ValueError("state 视频尺寸或帧数非法")
    if state["chunks_total"] <= 0 or not 0 <= state["chunks_done"] <= state["chunks_total"]:
        raise ValueError("state 分块进度非法")
    expected_chunks = (state["total_frames"] + CHUNK_FRAMES - 1) // CHUNK_FRAMES
    if state["chunks_total"] != expected_chunks:
        raise ValueError("state.chunks_total 与 total_frames 不一致")
    if not 0 <= state["current_chunk"] <= state["chunks_total"]:
        raise ValueError("state.current_chunk 非法")
    if state["current_chunk"] != state["chunks_done"]:
        raise ValueError("state.current_chunk 与 chunks_done 不一致")
    prompt_id = state.get("current_prompt_id")
    if prompt_id is not None and not isinstance(prompt_id, str):
        raise ValueError("state.current_prompt_id 非法")
    if state["chunks_done"] >= state["chunks_total"] and prompt_id is not None:
        raise ValueError("已完成任务不能保留 current_prompt_id")
    return state


def _output_state(state: Dict[str, Any], status: str, message: str,
                  error: str = "") -> None:
    """输出由 LLM 保存并原样传回的超分续跑信息。"""
    result: Dict[str, Any] = {
        "success": not error,
        "status": status,
        "progress": f"{state['chunks_done']}/{state['chunks_total']}",
        "state": state,
        "message": message,
    }
    if error:
        result["error"] = error
    print(json.dumps(result, ensure_ascii=False))


def _link_or_copy(src: Path, dst: Path) -> None:
    """优先硬链接，跨文件系统时回退复制。"""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _run_ffmpeg(ffmpeg: str, args: List[str], description: str) -> None:
    """执行 ffmpeg 并将错误转成可读异常。"""
    try:
        subprocess.run(args, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        detail = e.stderr.decode("utf-8", "replace")[-300:] if e.stderr else ""
        raise RuntimeError(f"{description}失败: {detail}")


def _prepare_source(run_dir: Path, src_path: Path, ffmpeg: str) -> Dict[str, int]:
    """拆源视频帧并探测尺寸；已有完整帧目录时直接复用。"""
    frames_dir = run_dir / "source_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames = sorted(frames_dir.glob("f_*.png"))
    if not frames:
        _run_ffmpeg(ffmpeg, [ffmpeg, "-y", "-i", str(src_path), str(frames_dir / "f_%05d.png")], "视频拆帧")
        frames = sorted(frames_dir.glob("f_*.png"))
    if not frames:
        raise RuntimeError("拆帧失败：0 帧")
    with Image.open(frames[0]) as image:
        width, height = image.size
    return {"total_frames": len(frames), "source_width": width, "source_height": height}


def _prepare_chunk(run_dir: Path, state: Dict[str, Any], chunk_idx: int,
                   ffmpeg: str) -> Path:
    """将指定源帧块编码为 ComfyUI 输入视频，并复用已存在文件。"""
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = input_dir / f"chunk_{chunk_idx:03d}.mp4"
    if chunk_path.exists():
        return chunk_path
    seq_dir = input_dir / f"seq_{chunk_idx:03d}"
    seq_dir.mkdir(parents=True, exist_ok=True)
    start = chunk_idx * CHUNK_FRAMES
    end = min(start + CHUNK_FRAMES, state["total_frames"])
    source_dir = run_dir / "source_frames"
    for frame_idx in range(start, end):
        source = source_dir / f"f_{frame_idx + 1:05d}.png"
        if not source.exists():
            raise RuntimeError(f"源帧缺失: {source.name}")
        target = seq_dir / f"f_{frame_idx - start + 1:04d}.png"
        if not target.exists():
            _link_or_copy(source, target)
    _run_ffmpeg(ffmpeg, [
        ffmpeg, "-y", "-framerate", str(FRAME_RATE), "-i", str(seq_dir / "f_%04d.png"),
        "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(chunk_path),
    ], f"第 {chunk_idx + 1} 块编码")
    return chunk_path


def _submit_chunk(state: Dict[str, Any], run_dir: Path, ffmpeg: str) -> None:
    """提交当前块，并把 ComfyUI prompt_id 写回 state。"""
    chunk_idx = state["current_chunk"]
    chunk_path = _prepare_chunk(run_dir, state, chunk_idx, ffmpeg)
    fname = upload_video_to_comfyui(str(chunk_path))
    width = state["source_width"] * state["scale"]
    height = state["source_height"] * state["scale"]
    workflow = build_upscale_workflow(fname, width, height, f"upscale_{state['run_id']}_chunk{chunk_idx:03d}")
    state["current_prompt_id"] = submit_task(workflow)


def _extract_chunk(run_dir: Path, state: Dict[str, Any], chunk_idx: int,
                   data: bytes, ffmpeg: str) -> None:
    """保存并抽取 ComfyUI 输出块，校验帧数后合并到全局输出序列。"""
    output_dir = run_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = output_dir / f"chunk_{chunk_idx:03d}.mp4"
    chunk_path.write_bytes(data)
    chunk_frames_dir = output_dir / f"chunk_{chunk_idx:03d}_frames"
    chunk_frames_dir.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(ffmpeg, [ffmpeg, "-y", "-i", str(chunk_path), str(chunk_frames_dir / "f_%04d.png")],
                f"第 {chunk_idx + 1} 块抽帧")
    frames = sorted(chunk_frames_dir.glob("f_*.png"))
    expected = min(CHUNK_FRAMES, state["total_frames"] - chunk_idx * CHUNK_FRAMES)
    if len(frames) != expected:
        raise RuntimeError(f"第 {chunk_idx + 1} 块输出帧数异常：得到 {len(frames)}，应为 {expected}")
    for offset, frame in enumerate(frames):
        target = output_dir / f"f_{chunk_idx * CHUNK_FRAMES + offset + 1:05d}.png"
        if not target.exists():
            _link_or_copy(frame, target)


def _finalize(run_dir: Path, state: Dict[str, Any], src_path: Path,
              ffmpeg: str) -> bytes:
    """拼接全部超分帧并保留源视频音轨。"""
    output_dir = run_dir / "output"
    final_no_audio = run_dir / "final_noaudio.mp4"
    _run_ffmpeg(ffmpeg, [
        ffmpeg, "-y", "-framerate", str(FRAME_RATE), "-i", str(output_dir / "f_%05d.png"),
        "-frames:v", str(state["total_frames"]), "-c:v", "libx264", "-crf", "18",
        "-pix_fmt", "yuv420p", str(final_no_audio),
    ], "超分视频拼接")
    probe = subprocess.run([ffmpeg, "-i", str(src_path)], capture_output=True)
    has_audio = b"Audio:" in probe.stderr
    final = run_dir / "final.mp4"
    if has_audio:
        _run_ffmpeg(ffmpeg, [
            ffmpeg, "-y", "-i", str(final_no_audio), "-i", str(src_path),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy",
            "-shortest", str(final),
        ], "原音轨合成")
    else:
        shutil.copy2(final_no_audio, final)
    return final.read_bytes()


def _new_state(session_id: str, source_video: str, scale: int,
               metadata: Dict[str, int], run_id: str) -> Dict[str, Any]:
    """创建首个 chunk 尚未提交的 state。"""
    total = metadata["total_frames"]
    return {
        "version": STATE_VERSION,
        "kind": STATE_KIND,
        "session_id": session_id,
        "run_id": run_id,
        "source_video": source_video,
        "scale": scale,
        "chunk_frames": CHUNK_FRAMES,
        "source_fps": FRAME_RATE,
        "source_width": metadata["source_width"],
        "source_height": metadata["source_height"],
        "total_frames": total,
        "chunks_total": (total + CHUNK_FRAMES - 1) // CHUNK_FRAMES,
        "chunks_done": 0,
        "current_chunk": 0,
        "current_prompt_id": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="视频超分（2x/4x，ESRGAN anime_6B）")
    parser.add_argument("--video", default="", help="会话内视频标识符（如 <ai_video_N>）")
    parser.add_argument("--scale", type=int, default=2, choices=[2, 4], help="放大倍数（默认 2）")
    parser.add_argument("--wait", type=int, default=240, help="本次等待秒数（默认 240，最大 540）")
    parser.add_argument("--state", default="", help="LLM 上次返回的 state JSON（续跑时原样传回）")
    args = parser.parse_args()
    args.wait = min(max(args.wait, 1), 540)

    session_id = os.environ.get("SESSION_ID", "unknown")
    store = VideoStoreCore(session_id)
    state: Optional[Dict[str, Any]] = None
    try:
        ffmpeg = find_ffmpeg()
        if args.state:
            state = _validate_state(args.state, session_id)
            src_path = _state_video_path(store, state["source_video"], "source_video")
            run_dir = _run_dir(state["run_id"])
            run_dir.mkdir(parents=True, exist_ok=True)

            prompt_id = state.get("current_prompt_id")
            if prompt_id:
                result = poll_result(prompt_id, args.wait)
                if result["status"] == "pending":
                    _output_state(state, "partial", "当前块仍在 ComfyUI 队列中，请原样传回 state 继续查询")
                    return
                if result["status"] == "error":
                    state["current_prompt_id"] = None
                    _output_state(state, "error", "当前块生成失败，请原样传回 state 重试",
                                  result.get("error", "ComfyUI 任务失败"))
                    return
                _extract_chunk(run_dir, state, state["current_chunk"], result["data"], ffmpeg)
                state["chunks_done"] += 1
                state["current_chunk"] = state["chunks_done"]
                state["current_prompt_id"] = None

            if state["chunks_done"] >= state["chunks_total"]:
                data = _finalize(run_dir, state, src_path, ffmpeg)
                entry = store.store_bytes(data, "ai", "mp4")
                output_result(True, identifier=entry.identifier, path=str(entry.file_path),
                              model=f"upscale_{state['scale']}x")
                return

            _submit_chunk(state, run_dir, ffmpeg)
            _output_state(state, "partial", "下一块已提交，请原样传回 state 查询进度")
            return

        if not args.video:
            output_error("--video 或 --state 参数必填")
            return
        src_path = _state_video_path(store, args.video.strip(), "source_video")
        run_id = uuid.uuid4().hex[:12]
        run_dir = _run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        metadata = _prepare_source(run_dir, src_path, ffmpeg)
        state = _new_state(session_id, args.video.strip(), args.scale, metadata, run_id)
        _submit_chunk(state, run_dir, ffmpeg)
        _output_state(state, "partial", "第 1 块已提交，请原样传回 state 查询进度")
    except (RuntimeError, ValueError, OSError) as e:
        if state is not None:
            _output_state(state, "error", "超分任务未完成，请原样传回 state 重试", str(e))
        else:
            output_error(f"超分失败: {e}")


if __name__ == "__main__":
    main()
