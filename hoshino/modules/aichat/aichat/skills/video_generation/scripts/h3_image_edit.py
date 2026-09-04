"""H3 本地图像编辑：参考图首帧锚定生成短视频，抽稳定帧交付图片

用法:
    python h3_image_edit.py --images <标识符> --prompt "<编辑指令>"

原理:
    H3 i2v 首帧是 keyframe 条件（非像素锚定），模型会按指令重绘画面——
    输入图 + "编辑后的最终画面"描述 → 39 帧短片段 → 抽后段 3 帧按清晰度选最优交付。

提示词协议（编辑版三段式）:
    - integrated_multimodal_description 描述"编辑后的最终画面"（不是操作过程），
      显式列出保留项（人物特征/光线/构图）+ static shot/no motion 抑制运动
    - overall_soundscape / non_diegetic_music 用 silent / none（图像编辑无需音频）
"""
import argparse
import copy
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comfyui_video as cv  # noqa: E402
from _common import (  # noqa: E402
    resolve_image_file, store_image, output_result, output_error,
)

os.environ.setdefault("PROJECT_ROOT", "/root/bot/shebot_nb2")

EDIT_FRAMES = 39       # 最短合法片段（17k+5 网格，≈1.6s）
CANDIDATE_FRAMES = (25, 31, 37)  # 候选抽帧位置（后段，编辑演变完成区）


def _sharpen_score(frame_path: str) -> float:
    """拉普拉斯方差清晰度（PIL + numpy，无 cv2 依赖）"""
    import numpy as np
    from PIL import Image

    img = np.asarray(Image.open(frame_path).convert("L"), dtype=np.float64)
    lap = (
        -4 * img[1:-1, 1:-1]
        + img[:-2, 1:-1] + img[2:, 1:-1]
        + img[1:-1, :-2] + img[1:-1, 2:]
    )
    return float(lap.var())


def _extract_frame(video_path: str, frame_idx: int, out_path: str, ffmpeg: str) -> bool:
    """ffmpeg 抽单帧"""
    import subprocess
    r = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-i", video_path,
         "-vf", f"select='eq(n\\,{frame_idx})'", "-vsync", "0", out_path],
        capture_output=True, text=True)
    return r.returncode == 0 and Path(out_path).exists()


def main() -> None:
    parser = argparse.ArgumentParser(description="H3 本地图像编辑（i2v 锚定 + 抽帧）")
    parser.add_argument("--model", choices=["hybrid", "official"], default="hybrid",
                        help="模型版本：hybrid=融合模型（默认），official=官方")
    parser.add_argument("--images", default="", help="输入图标识符（SKILL_IMAGES 解析，单张）")
    parser.add_argument("--prompt", default="", help="编辑指令（描述编辑后的最终画面）")
    parser.add_argument("--resolution", choices=list(cv.RESOLUTION_PIXELS.keys()), default="480p")
    parser.add_argument("--steps", type=int, default=8, help="采样步数（默认 8）")
    parser.add_argument("--lora-strength", type=float, default=0.5,
                        help="MysticXXX LoRA 强度（0=关闭，默认 0.5）")
    parser.add_argument("--frames", type=int, default=EDIT_FRAMES,
                        help="生成帧数（默认 39≈1.6s；17k+5 网格）")
    parser.add_argument("--prompt-id", default="", help="续查已提交任务的 prompt_id")
    parser.add_argument("--wait", type=int, default=240, help="本次等待秒数")
    args = parser.parse_args()

    # 幂等续查：任务完成后交付同一结果
    # （编辑任务短，通常一次等待内完成；此分支供超时后恢复）
    if args.prompt_id:
        result = cv.poll_result(args.prompt_id, args.wait)
        if result["status"] == "pending":
            output_error(f"仍在生成中，请使用 --prompt-id {args.prompt_id} 继续查询")
            return
        if result["status"] == "error":
            output_error(result.get("error", "ComfyUI 任务失败"))
            return
        _deliver_frames(result["data"], args.prompt_id)
        return

    if not args.prompt:
        output_error("--prompt 必填（编辑指令）")
        return
    if not args.images:
        output_error("需要 --images 输入图标识符")
        return

    path = resolve_image_file(args.images)
    if not path:
        output_error(f"未找到图片标识符: {args.images}")
        return

    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"

    # ---- 构建 i2v 工作流（hybrid 模型，首帧锚定）----
    try:
        wf = copy.deepcopy(cv.load_workflow(cv.TASK_WORKFLOW["i2v"]))
    except RuntimeError as e:
        output_error(str(e))
        return
    cv._replace_scalar(wf, "{{unet_name}}", cv.model_checkpoint("i2v", args.model))
    cv.apply_prompt(wf, args.prompt)
    cv.apply_length(wf, args.frames)
    cv.apply_steps(wf, args.steps)
    cv.apply_mystic_lora(wf, args.lora_strength)

    # 编辑是静态画面：去掉 SigmaRefiner 尾段加步（省 ~40% 时间，静态无需运动细化）
    if "85" in wf and wf["85"].get("class_type") == "H3SigmaRefiner":
        wf["81"]["inputs"]["sigmas"] = ["84", 0]
        wf.pop("85", None)

    # 尺寸：按输入图比例（480p 档像素上限）
    try:
        width, height = cv.compute_target_size(path, max_pixels=cv.RESOLUTION_PIXELS[args.resolution])
        uploaded = [cv.upload_image_to_comfyui(path)]
    except Exception as e:
        output_error(f"图片上传失败: {e}")
        return
    cv.apply_size(wf, width, height)
    cv._apply_anchors(wf, first_name=uploaded[0])

    # ---- 提交并等待 ----
    try:
        prompt_id = cv.submit_task(wf)
    except RuntimeError as e:
        output_error(str(e))
        return
    result = cv.poll_result(prompt_id, args.wait)
    if result["status"] == "pending":
        output_error(f"仍在生成中，请使用 --prompt-id {prompt_id} 继续查询")
        return
    if result["status"] == "error":
        output_error(result.get("error", "ComfyUI 任务失败"))
        return
    _deliver_frames(result["data"], prompt_id)


def _deliver_frames(video_bytes: bytes, prompt_id: str) -> None:
    """抽候选帧选最优，存入 ImageStore 交付"""
    session_dir = os.environ.get("SESSION_TMP_DIR") or tempfile.mkdtemp(prefix="h3edit_")
    video_path = Path(session_dir) / f"{prompt_id[:12]}.mp4"
    video_path.write_bytes(video_bytes)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"

    best_path, best_score = None, -1.0
    for idx in CANDIDATE_FRAMES:
        frame_path = Path(session_dir) / f"{prompt_id[:12]}_{idx}.png"
        if not _extract_frame(str(video_path), idx, str(frame_path), ffmpeg):
            continue
        score = _sharpen_score(str(frame_path))
        if score > best_score:
            best_score, best_path = score, frame_path

    if best_path is None:
        output_error("抽帧失败：无法从生成结果提取帧")
        return

    entry = store_image(best_path.read_bytes(), "ai", "png")
    output_result(True, identifier=entry["identifier"], path=entry["path"],
                  model="h3_image_edit")


if __name__ == "__main__":
    main()
