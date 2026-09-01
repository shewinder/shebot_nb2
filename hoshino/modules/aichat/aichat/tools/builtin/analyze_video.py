"""视频分析工具：抽取临时帧并交给 vision subagent 分析。

抽取帧只存在于本次 API 请求的内存中，不写入 ImageStore，因此不会触发回复管道的图片自动补发。
"""
import asyncio
import base64
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel, Field

from ...agent_loop import AgentTask, run_agent_loop
from ...subagent_types import SUBAGENT_TYPES
from ..registry import tool_registry, ok, fail

if TYPE_CHECKING:
    from ...session import Session


MAX_FRAMES = 8
MAX_FRAME_BYTES = 1_500_000
MAX_TOTAL_FRAME_BYTES = 8_000_000
FRAME_TIMEOUT = 30
PROBE_TIMEOUT = 15
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):([\d.]+)")


class AnalyzeVideoInput(BaseModel):
    """视频分析工具输入模型"""

    video_identifier: str = Field(
        min_length=1,
        max_length=128,
        description="会话内视频标识符，如 <user_video_1> 或 <ai_video_1>",
    )
    question: str = Field(
        min_length=1,
        max_length=2000,
        description="希望从视频中分析的问题或目标",
    )
    max_frames: int = Field(
        default=6,
        ge=1,
        le=MAX_FRAMES,
        description=f"均匀抽取的帧数（默认 6，最大 {MAX_FRAMES}）",
    )


def _find_ffmpeg() -> Optional[str]:
    """定位 ffmpeg：系统 PATH。"""
    return shutil.which("ffmpeg")


async def _probe_duration(ffmpeg: str, video_path: Path) -> Optional[float]:
    """读取视频时长；ffmpeg 的媒体探测会以非零状态退出，按 stderr 解析即可。"""
    process = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-hide_banner",
        "-i",
        str(video_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=PROBE_TIMEOUT)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return None

    output = stderr.decode("utf-8", errors="replace")
    match = _DURATION_RE.search(output)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return duration if duration > 0 else None


async def _extract_frame(ffmpeg: str, video_path: Path, timestamp: float) -> bytes:
    """从指定时间点抽取压缩帧，直接通过 stdout 返回，避免落盘为 ai_image。"""
    process = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-vf",
        "scale=1280:1280:force_original_aspect_ratio=decrease",
        "-f",
        "image2pipe",
        "-vcodec",
        "mjpeg",
        "-q:v",
        "6",
        "pipe:1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=FRAME_TIMEOUT)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("抽帧超时")

    if process.returncode != 0 or not stdout:
        detail = stderr.decode("utf-8", errors="replace").strip()[:200]
        raise RuntimeError(f"ffmpeg 抽帧失败{f': {detail}' if detail else ''}")
    if len(stdout) > MAX_FRAME_BYTES:
        raise RuntimeError(f"抽取帧过大（>{MAX_FRAME_BYTES // 1024}KB）")
    return stdout


def _build_analysis_prompt(
    identifier: str,
    question: str,
    timestamps: List[float],
) -> str:
    """构建带帧序号和时间戳的视觉分析任务。"""
    frame_lines = "\n".join(
        f"- 第 {index} 帧：{timestamp:.2f}s"
        for index, timestamp in enumerate(timestamps, start=1)
    )
    return (
        "【视频分析任务】\n"
        f"视频标识符：{identifier}\n"
        "以下图片按视频时间顺序排列，每张图片对应一个抽样时间点：\n"
        f"{frame_lines}\n\n"
        f"用户问题：{question}\n\n"
        "请只根据这些视频帧回答。明确区分直接观察到的内容与无法从抽样帧确定的推测；"
        "不要输出图片标识符，也不要声称看到了未提供的连续动作或音频。"
    )


@tool_registry.register(
    description="""分析会话内的视频内容。

工具会从 <user_video_N>/<ai_video_N> 均匀抽取若干帧，交给视觉子 Agent 分析，返回文字结果。
抽取帧仅用于本次分析，不会生成或发送图片标识符；当前版本只分析画面，不识别音频。""",
)
async def analyze_video(
    params: AnalyzeVideoInput,
    session: Optional["Session"] = None,
) -> Dict[str, Any]:
    """抽取视频帧并调用 vision subagent。"""
    if session is None:
        return fail("无法获取会话上下文", error="Missing session")

    identifier = params.video_identifier.strip()
    question = params.question.strip()
    if not identifier:
        return fail("视频标识符不能为空")
    if not question:
        return fail("分析问题不能为空")

    video_path = session.resolve_video_file(identifier)
    if video_path is None or not video_path.is_file():
        return fail(f"未找到视频标识符: {identifier}")

    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return fail("系统未找到 ffmpeg，无法分析视频")

    duration = await _probe_duration(ffmpeg, video_path)
    if duration is None:
        return fail("无法读取视频时长，视频可能已损坏或格式不受支持")

    timestamps = [
        duration * (index + 0.5) / params.max_frames
        for index in range(params.max_frames)
    ]
    frame_data_urls: List[str] = []
    extracted_timestamps: List[float] = []
    total_bytes = 0
    for timestamp in timestamps:
        try:
            frame = await _extract_frame(ffmpeg, video_path, timestamp)
        except RuntimeError as exc:
            logger.warning(f"[analyze_video] 抽取 {timestamp:.2f}s 失败: {exc}")
            continue
        if total_bytes + len(frame) > MAX_TOTAL_FRAME_BYTES:
            logger.warning("[analyze_video] 达到临时帧总大小上限，停止继续抽帧")
            break
        frame_data_urls.append(
            f"data:image/jpeg;base64,{base64.b64encode(frame).decode('ascii')}"
        )
        extracted_timestamps.append(timestamp)
        total_bytes += len(frame)

    if not frame_data_urls:
        return fail("视频抽帧失败，无法进行画面分析")

    task = AgentTask(
        task=_build_analysis_prompt(identifier, question, extracted_timestamps),
        system_prompt=SUBAGENT_TYPES["vision"].system_prompt,
        user_id=session.user_id,
        group_id=session.group_id,
        profile="vision",
        max_rounds=1,
        tools=[],
        image_data_urls=frame_data_urls,
        session_prefix=f"video_analysis_{session.session_id}",
        label="sub:video",
        blocked_tools=frozenset({"run_background_task", "delegate_task", "schedule_task"}),
        locked_tools=True,
    )

    agent_result = None
    try:
        agent_result = await run_agent_loop(task)
        result = agent_result.result
        if result.error:
            return fail(f"视频分析失败: {result.error}", error=str(result.error))
        content = (result.content or "").strip()
        if not content:
            return fail("视觉子 Agent 未返回分析结果")
        return ok(
            content,
            metadata={
                "video": identifier,
                "duration": round(duration, 2),
                "requested_frames": params.max_frames,
                "extracted_frames": len(frame_data_urls),
                "timestamps": [round(value, 2) for value in extracted_timestamps],
            },
        )
    finally:
        if agent_result is not None:
            agent_result.session.dispose()
