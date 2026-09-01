"""视频超分续跑协议测试。

用法：.venv/bin/python test/aichat/test_upscale_video.py
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).parents[2].resolve()
SCRIPT = PROJECT_ROOT / "hoshino/modules/aichat/aichat/skills/video_generation/scripts/upscale_video.py"
os.environ.setdefault("PROJECT_ROOT", str(PROJECT_ROOT))
spec = importlib.util.spec_from_file_location("test_upscale_video_module", SCRIPT)
upscale = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = upscale
spec.loader.exec_module(upscale)


class FakeStore:
    def __init__(self, session_id: str):
        self.session_id = session_id

    def store_bytes(self, data: bytes, source: str, ext: str) -> Any:
        return SimpleNamespace(identifier="<ai_video_final>", file_path=Path("/session/final.mp4"))


def make_state(**overrides: Any) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "version": 1,
        "kind": "video_upscale",
        "session_id": "session_test",
        "run_id": "0123456789ab",
        "source_video": "<ai_video_1>",
        "scale": 2,
        "chunk_frames": 24,
        "source_fps": 24,
        "source_width": 864,
        "source_height": 480,
        "total_frames": 48,
        "chunks_total": 2,
        "chunks_done": 0,
        "current_chunk": 0,
        "current_prompt_id": "prompt-1",
    }
    state.update(overrides)
    return state


class TestUpscaleState(unittest.TestCase):
    def test_workflow_uses_target_dimensions_and_fixed_fps(self):
        workflow = upscale.build_upscale_workflow("chunk.mp4", 1728, 960, "prefix")
        self.assertEqual(workflow["1"]["inputs"]["file"], "chunk.mp4")
        self.assertEqual(workflow["5"]["inputs"]["width"], 1728)
        self.assertEqual(workflow["5"]["inputs"]["height"], 960)
        self.assertEqual(workflow["6"]["inputs"]["fps"], 24.0)
        self.assertEqual(workflow["7"]["inputs"]["filename_prefix"], "prefix")

    def test_state_validation_rejects_other_session_and_inconsistent_progress(self):
        with self.assertRaisesRegex(ValueError, "当前会话"):
            upscale._validate_state(json.dumps(make_state(session_id="other")), "session_test")
        with self.assertRaisesRegex(ValueError, "current_chunk"):
            upscale._validate_state(json.dumps(make_state(current_chunk=1)), "session_test")
        with self.assertRaisesRegex(ValueError, "chunks_total"):
            upscale._validate_state(json.dumps(make_state(chunks_total=3)), "session_test")

    def test_tmp_fallback_remains_inside_session_directory(self):
        with patch.dict(os.environ, {
            "PROJECT_ROOT": "/project",
            "SESSION_ID": "session_test",
        }, clear=True):
            self.assertEqual(
                upscale._session_tmp_dir(),
                Path("/project/data/aichat/sessions/session_test/tmp"),
            )

    def test_pending_returns_partial_state(self):
        state = make_state()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "SESSION_ID": "session_test",
            "SESSION_TMP_DIR": tmp,
        }), patch.object(upscale, "find_ffmpeg", return_value="ffmpeg"), \
                patch.object(upscale, "_state_video_path", return_value=Path(tmp) / "source.mp4"), \
                patch.object(upscale, "poll_result", return_value={"status": "pending"}):
            old_argv = sys.argv
            sys.argv = [str(SCRIPT), "--state", json.dumps(state)]
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    upscale.main()
            finally:
                sys.argv = old_argv
        result = json.loads(output.getvalue())
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["state"], state)
        self.assertEqual(result["progress"], "0/2")

    def test_completed_chunk_advances_and_submits_next_chunk(self):
        state = make_state()
        submitted = []

        def submit_next(current: Dict[str, Any], run_dir: Path, ffmpeg: str) -> None:
            submitted.append(current["current_chunk"])
            current["current_prompt_id"] = "prompt-2"

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "SESSION_ID": "session_test",
            "SESSION_TMP_DIR": tmp,
        }), patch.object(upscale, "find_ffmpeg", return_value="ffmpeg"), \
                patch.object(upscale, "_state_video_path", return_value=Path(tmp) / "source.mp4"), \
                patch.object(upscale, "poll_result", return_value={"status": "done", "data": b"chunk"}), \
                patch.object(upscale, "_extract_chunk"), \
                patch.object(upscale, "_submit_chunk", side_effect=submit_next):
            old_argv = sys.argv
            sys.argv = [str(SCRIPT), "--state", json.dumps(state)]
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    upscale.main()
            finally:
                sys.argv = old_argv
        result = json.loads(output.getvalue())
        self.assertEqual(submitted, [1])
        self.assertEqual(result["state"]["chunks_done"], 1)
        self.assertEqual(result["state"]["current_chunk"], 1)
        self.assertEqual(result["state"]["current_prompt_id"], "prompt-2")
        self.assertEqual(result["progress"], "1/2")

    def test_last_chunk_stores_only_final_video(self):
        state = make_state(chunks_total=1, total_frames=24)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "SESSION_ID": "session_test",
            "SESSION_TMP_DIR": tmp,
        }), patch.object(upscale, "VideoStoreCore", FakeStore), \
                patch.object(upscale, "find_ffmpeg", return_value="ffmpeg"), \
                patch.object(upscale, "_state_video_path", return_value=Path(tmp) / "source.mp4"), \
                patch.object(upscale, "poll_result", return_value={"status": "done", "data": b"chunk"}), \
                patch.object(upscale, "_extract_chunk"), \
                patch.object(upscale, "_finalize", return_value=b"final"):
            old_argv = sys.argv
            sys.argv = [str(SCRIPT), "--state", json.dumps(state)]
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    upscale.main()
            finally:
                sys.argv = old_argv
        result = json.loads(output.getvalue())
        self.assertTrue(result["success"])
        self.assertEqual(result["identifier"], "<ai_video_final>")
        self.assertEqual(result["model"], "upscale_2x")

    def test_prepare_source_normalizes_non_24fps(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg/ffprobe 未安装")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source_30fps.mp4"
            subprocess.run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                "-i", "testsrc=size=160x90:rate=30:duration=1", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-y", str(source),
            ], check=True, capture_output=True)
            metadata = upscale._prepare_source(root, source, ffmpeg)
            duration = float(subprocess.check_output([
                ffprobe, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", str(root / "source_24fps.mp4"),
            ], text=True).strip())
            self.assertEqual(metadata["total_frames"], 24)
            self.assertAlmostEqual(duration, 1.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
