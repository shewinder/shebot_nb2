#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-08-26
Description: 视频超分（RealESRGAN anime_6B，2x），供 video_generation SKILL 使用

用法：
    upscale_video.py --video <ai_video_N> [--scale 2] [--wait 540]

- 解析会话内视频标识符（复用 VideoStoreCore）
- 拆帧后按 24 帧/块逐块提交 ComfyUI：ESRGAN 4x 超分 + 缩放到目标倍数（防整片 batch 爆显存）
- 拼接全部超分帧，保留原音轨（-c:a copy）
- 存回会话 VideoStore，返回新 <ai_video_N>
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from comfyui_video import (
    submit_task, poll_result, upload_image_to_comfyui,
    output_result, output_error,
)
from comfyui_video_chain import upload_video_to_comfyui

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

COMFYUI_BASE_URL = os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188")

# 固定分块：24 帧/块（ESRGAN 4x 输出每帧约 196MB，24 帧 ≈ 4.7GB，16GB 显存安全）
CHUNK_FRAMES = 24


def find_ffmpeg() -> str:
    """定位 ffmpeg：优先 ComfyUI venv 的 imageio-ffmpeg 自带二进制，其次 PATH"""
    candidates: List[str] = []
    # ComfyUI venv 常见路径
    comfyui_venv = Path("/root/bot/comfyui/.venv")
    if comfyui_venv.exists():
        p = comfyui_venv / "lib" / "python3.14" / "site-packages" / "imageio_ffmpeg" / "binaries"
        if p.exists():
            bins = sorted(p.glob("ffmpeg-*"))
            if bins:
                candidates.append(str(bins[0]))
    import shutil
    which = shutil.which("ffmpeg")
    if which:
        candidates.append(which)
    if not candidates:
        raise RuntimeError("未找到 ffmpeg（ComfyUI venv 与 PATH 均无）")
    return candidates[0]


def build_upscale_workflow(fname: str, width: int, height: int, prefix: str) -> dict:
    """单块超分工作流：LoadVideo -> ESRGAN 4x -> ImageScale 目标尺寸 -> CreateVideo -> SaveVideo"""
    return {
        "1": {"class_type": "LoadVideo", "inputs": {"file": fname}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "3": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "RealESRGAN_x4plus_anime_6B.pth"}},
        "4": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["3", 0], "image": ["2", 0]}},
        "5": {"class_type": "ImageScale", "inputs": {
            "image": ["4", 0], "upscale_method": "lanczos",
            "width": width, "height": height, "crop": "disabled"}},
        "6": {"class_type": "CreateVideo", "inputs": {"images": ["5", 0], "fps": 24.0, "bit_depth": 8}},
        "7": {"class_type": "SaveVideo", "inputs": {"video": ["6", 0],
              "filename_prefix": prefix, "format": "mp4", "codec": "auto"}},
    }


def upscale_video(src_path: str, scale: int, wait: int) -> bytes:
    """拆帧 -> 分块超分 -> 拼接 -> mux 原音轨，返回最终 mp4 bytes"""
    ffmpeg = find_ffmpeg()
    tmp = tempfile.mkdtemp(prefix="upscale_")
    frames_dir = Path(tmp) / "frames"
    out_dir = Path(tmp) / "out"
    frames_dir.mkdir()
    out_dir.mkdir()

    # 1. 拆帧
    subprocess.run([ffmpeg, "-y", "-i", src_path, f"{frames_dir}/f_%04d.png"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    frames = sorted(p.name for p in frames_dir.iterdir())
    total = len(frames)
    if total == 0:
        raise RuntimeError("拆帧失败：0 帧")
    # 2. 读取源尺寸
    from PIL import Image
    with Image.open(frames_dir / frames[0]) as im:
        src_w, src_h = im.size
    width, height = src_w * scale, src_h * scale

    # 3. 分块超分
    chunks = (total + CHUNK_FRAMES - 1) // CHUNK_FRAMES
    for ci in range(chunks):
        start, end = ci * CHUNK_FRAMES, min((ci + 1) * CHUNK_FRAMES, total)
        seq = Path(tmp) / f"seq_{ci:03d}"
        seq.mkdir()
        for i in range(start, end):
            os.link(frames_dir / frames[i], seq / f"f_{i - start + 1:04d}.png")
        chunk_video = Path(tmp) / f"chunk_{ci:03d}.mp4"
        subprocess.run([ffmpeg, "-y", "-framerate", "24", "-i", f"{seq}/f_%04d.png",
                        "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(chunk_video)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        fname = upload_video_to_comfyui(str(chunk_video))
        wf = build_upscale_workflow(fname, width, height, f"upscale_chunk{ci:03d}")
        pid = submit_task(wf)
        result = poll_result(pid, wait)
        if result["status"] != "done":
            raise RuntimeError(f"块 {ci + 1}/{chunks} 失败: {result.get('error', result)}")
        chunk_out = Path(tmp) / f"chunk_out_{ci:03d}.mp4"
        chunk_out.write_bytes(result["data"])
        cf_dir = Path(tmp) / f"cf_{ci:03d}"
        cf_dir.mkdir()
        subprocess.run([ffmpeg, "-y", "-i", str(chunk_out), f"{cf_dir}/c_%04d.png"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        for i, fr in enumerate(sorted(p.name for p in cf_dir.iterdir())):
            os.link(cf_dir / fr, out_dir / f"f_{start + i + 1:05d}.png")

    # 4. 拼接
    video_no_audio = Path(tmp) / "final_noaudio.mp4"
    subprocess.run([ffmpeg, "-y", "-framerate", "24", "-i", f"{out_dir}/f_%05d.png",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(video_no_audio)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    # 5. mux 原音轨（有音轨才 mux，无音轨直接返回视频）
    probe = subprocess.run([ffmpeg, "-i", src_path], capture_output=True)
    has_audio = b"Audio:" in probe.stderr
    final = Path(tmp) / "final.mp4"
    if has_audio:
        subprocess.run([ffmpeg, "-y", "-i", str(video_no_audio), "-i", src_path,
                        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy",
                        "-shortest", str(final)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    else:
        os.replace(video_no_audio, final)
    return final.read_bytes()


def main() -> None:
    parser = argparse.ArgumentParser(description="视频超分（2x，ESRGAN anime_6B）")
    parser.add_argument("--video", required=True, help="会话内视频标识符（如 <ai_video_N>）")
    parser.add_argument("--scale", type=int, default=2, choices=[2, 4], help="放大倍数（默认 2）")
    parser.add_argument("--wait", type=int, default=540, help="单块等待秒数（默认 540）")
    args = parser.parse_args()

    session_id = os.environ.get("SESSION_ID", "unknown")
    store = VideoStoreCore(session_id)
    src_path = store.get_file_path(args.video)
    if not src_path:
        output_error(f"未找到视频标识符: {args.video}")
        return

    try:
        data = upscale_video(str(src_path), args.scale, args.wait)
    except Exception as e:
        output_error(f"超分失败: {e}")
        return

    entry = store.store_bytes(data, "ai", "mp4")
    output_result(True, identifier=entry.identifier, path=str(entry.file_path),
                  model=f"upscale_{args.scale}x")


if __name__ == "__main__":
    main()
