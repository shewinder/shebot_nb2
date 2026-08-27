#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-08-27
Description: 视频工具（抽帧/规格/裁剪），供 video_generation SKILL 使用

LLM 需要"看"视频或处理视频时调用本脚本，禁止自写 ffmpeg 脚本：

    video_tools.py --probe --video <user_video_1>          # 规格：时长/分辨率/帧率/大小
    video_tools.py --extract-frame --video <user_video_1> --at 3.0   # 抽帧 → <ai_image_N>
    video_tools.py --cut --video <user_video_1> --start 1.0 --duration 5  # 裁剪 → <ai_video_N>

- 视频标识符通过 SKILL_VIDEOS 环境变量解析（execute_script 注入）
- 抽帧结果存 ImageStore（<ai_image_N>，LLM 可直接引用让模型看画面）
- 裁剪结果存 VideoStore（<ai_video_N>），保留原音轨
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_IG_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "image_generation" / "scripts"
sys.path.insert(0, str(_IG_SCRIPTS))

from _common import store_image, output_result, output_error

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


def get_video_paths() -> Dict[str, str]:
    """从 SKILL_VIDEOS 环境变量获取标识符→路径映射"""
    raw = os.environ.get("SKILL_VIDEOS", "{}")
    try:
        return json.loads(raw)
    except Exception:
        return {}


def resolve_video_file(identifier: str) -> Optional[str]:
    """将视频标识符解析为本地文件路径"""
    identifier = identifier.strip()
    if not identifier.startswith("<"):
        identifier = f"<{identifier}>"
    return get_video_paths().get(identifier)


def find_ffmpeg() -> str:
    """定位 ffmpeg：imageio_ffmpeg → PATH → ComfyUI venv"""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except ImportError:
        pass
    which = shutil.which("ffmpeg")
    if which:
        return which
    for candidate in sorted(Path("/root/bot/comfyui/.venv").glob("lib/*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*")):
        return str(candidate)
    raise RuntimeError("未找到 ffmpeg")


def probe_video(ffmpeg: str, src: str) -> Dict[str, Any]:
    """读取视频规格：时长/分辨率/帧率/大小"""
    out = subprocess.run(
        [ffmpeg, "-i", src], capture_output=True
    ).stderr.decode("utf-8", errors="replace")
    # 从 ffmpeg 输出解析
    duration, width, height, fps = None, None, None, None
    for line in out.splitlines():
        if "Duration:" in line and duration is None:
            d = line.split("Duration:")[1].split(",")[0].strip()
            hh, mm, ss = d.split(":")
            duration = int(hh) * 3600 + int(mm) * 60 + float(ss)
        if "Video:" in line:
            import re
            m = re.search(r"(\d{2,5})x(\d{2,5})", line)
            if m:
                width, height = int(m.group(1)), int(m.group(2))
            m = re.search(r"([\d.]+) fps", line)
            if m:
                fps = float(m.group(1))
    return {
        "duration": round(duration, 2) if duration else None,
        "width": width,
        "height": height,
        "fps": fps,
        "size_bytes": Path(src).stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="视频工具：规格/抽帧/裁剪")
    parser.add_argument("--probe", action="store_true", help="读取视频规格")
    parser.add_argument("--extract-frame", action="store_true", help="抽帧")
    parser.add_argument("--cut", action="store_true", help="裁剪片段")
    parser.add_argument("--video", required=True, help="视频标识符（如 <user_video_1>）")
    parser.add_argument("--at", type=float, default=0.0, help="抽帧时间点（秒，默认 0）")
    parser.add_argument("--start", type=float, default=0.0, help="裁剪起点（秒）")
    parser.add_argument("--duration", type=float, default=5.0, help="裁剪时长（秒，默认 5）")
    args = parser.parse_args()

    if not (args.probe or args.extract_frame or args.cut):
        output_error("请指定操作：--probe / --extract-frame / --cut")
        return

    src = resolve_video_file(args.video)
    if not src:
        output_error(f"未找到视频标识符: {args.video}")
        return

    try:
        ffmpeg = find_ffmpeg()
    except RuntimeError as e:
        output_error(str(e))
        return

    session_id = os.environ.get("SESSION_ID", "unknown")
    store = VideoStoreCore(session_id)

    if args.probe:
        try:
            info = probe_video(ffmpeg, src)
        except Exception as e:
            output_error(f"读取规格失败: {e}")
            return
        output_result(True, model="video_probe", error="",
                      identifier=args.video)
        # 规格放 stdout 附加行（output_result 只有固定字段，规格单独打印 JSON）
        print(json.dumps({"video": args.video, **info}, ensure_ascii=False))
        return

    if args.extract_frame:
        try:
            png = subprocess.run(
                [ffmpeg, "-y", "-ss", str(args.at), "-i", src, "-frames:v", "1", "-f", "image2", "pipe:1"],
                capture_output=True, check=True,
            ).stdout
        except subprocess.CalledProcessError as e:
            output_error(f"抽帧失败: {e.stderr.decode('utf-8', errors='replace')[:200]}")
            return
        stored = store_image(png, "ai", "png")
        output_result(True, identifier=stored["identifier"], path=stored["path"],
                      model="video_extract_frame")
        return

    # --cut（mp4 需要 seekable 输出，先写临时文件再读 bytes）
    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(tmp_fd)
    try:
        try:
            subprocess.run(
                [ffmpeg, "-y", "-ss", str(args.start), "-t", str(args.duration),
                 "-i", src, "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                 "-c:a", "aac", "-movflags", "+faststart", tmp_path],
                capture_output=True, check=True,
            )
        except subprocess.CalledProcessError as e:
            output_error(f"裁剪失败: {e.stderr.decode('utf-8', errors='replace')[:200]}")
            return
        mp4 = Path(tmp_path).read_bytes()
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    entry = store.store_bytes(mp4, "ai", "mp4")
    output_result(True, identifier=entry.identifier, path=str(entry.file_path),
                  model="video_cut")


if __name__ == "__main__":
    main()
