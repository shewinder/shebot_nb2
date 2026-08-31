"""视频分析工具测试：真实 ffmpeg 抽帧与临时多模态输入隔离。"""
import asyncio
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

import nonebot  # noqa: E402
nonebot.init()

sys.path.insert(0, str(_PROJECT_ROOT))

from hoshino.modules.aichat.aichat.agent_loop import AgentResult  # noqa: E402
from hoshino.modules.aichat.aichat.chat_executor import ChatResult  # noqa: E402
from hoshino.modules.aichat.aichat.tools.builtin import analyze_video as module  # noqa: E402
from hoshino.modules.aichat.aichat.tools.builtin.analyze_video import (  # noqa: E402
    AnalyzeVideoInput,
    _extract_frame,
    _probe_duration,
    analyze_video,
)


class TestFfmpegFrameExtraction(unittest.IsolatedAsyncioTestCase):
    async def test_probe_and_extract_jpeg_without_image_store(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg 未安装")

        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "sample.mp4"
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=red:s=320x240:d=1",
                    "-c:v",
                    "mpeg4",
                    "-y",
                    str(video_path),
                ],
                check=True,
                capture_output=True,
            )

            duration = await _probe_duration(ffmpeg, video_path)
            frame = await _extract_frame(ffmpeg, video_path, 0.5)

            self.assertIsNotNone(duration)
            self.assertAlmostEqual(duration or 0, 1.0, delta=0.1)
            self.assertTrue(frame.startswith(b"\xff\xd8"))
            self.assertTrue(frame.endswith(b"\xff\xd9"))
            self.assertEqual(list(Path(tmp_dir).iterdir()), [video_path])


class TestAnalyzeVideoTool(unittest.IsolatedAsyncioTestCase):
    async def test_passes_frames_as_transient_data_urls(self) -> None:
        child_session = SimpleNamespace(dispose=unittest.mock.Mock())
        agent_result = AgentResult(
            result=ChatResult(content="视频中是一片红色画面。"),
            session=child_session,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "input.mp4"
            video_path.write_bytes(b"video")
            session = SimpleNamespace(
                user_id=1,
                group_id=2,
                session_id="video_tool_test",
                resolve_video_file=lambda identifier: video_path,
            )

            with (
                patch.object(module, "_find_ffmpeg", return_value="ffmpeg"),
                patch.object(module, "_probe_duration", AsyncMock(return_value=4.0)),
                patch.object(
                    module,
                    "_extract_frame",
                    AsyncMock(return_value=b"\xff\xd8frame\xff\xd9"),
                ),
                patch.object(module, "run_agent_loop", AsyncMock(return_value=agent_result)) as run,
            ):
                result = await analyze_video(
                    AnalyzeVideoInput(
                        video_identifier="<user_video_1>",
                        question="画面里有什么？",
                        max_frames=3,
                    ),
                    session=session,
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["metadata"]["extracted_frames"], 3)
        task = run.await_args.args[0]
        self.assertEqual(task.image_identifiers, [])
        self.assertEqual(task.tools, [])
        self.assertEqual(len(task.image_data_urls), 3)
        self.assertTrue(all(url.startswith("data:image/jpeg;base64,") for url in task.image_data_urls))
        self.assertNotIn("<ai_image_", str(result))
        child_session.dispose.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
