"""视频生成 Skill 的 workflow 和续跑协议回归测试。"""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image


PROJECT_ROOT = Path(__file__).parents[2].resolve()
SCRIPTS = PROJECT_ROOT / "hoshino/modules/aichat/aichat/skills/video_generation/scripts"
os.environ.setdefault("PROJECT_ROOT", str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS))

video = importlib.import_module("comfyui_video")
chain = importlib.import_module("comfyui_video_chain")


class TestVideoWorkflow(unittest.TestCase):
    def _run_main(self, task: str, images: str, **extra: str):
        captured = {}
        with tempfile.TemporaryDirectory() as tmp:
            image_paths = {}
            for index, ident in enumerate(images.split(","), 1):
                path = Path(tmp) / f"image_{index}.png"
                Image.new("RGB", (320, 180), (index * 30, 50, 80)).save(path)
                image_paths[ident] = str(path)

            def capture_submit(workflow):
                captured["workflow"] = workflow
                return "prompt-test"

            argv = [
                "comfyui_video.py", "--task", task, "--images", images,
                "--prompt", "prompt", "--duration", "1", "--wait", "1",
            ]
            for key, value in extra.items():
                argv.extend([f"--{key.replace('_', '-')}", str(value)])
            with patch.dict(os.environ, {"SKILL_IMAGES": json.dumps({})}), \
                    patch.object(video, "resolve_image_file", side_effect=image_paths.get), \
                    patch.object(video, "upload_image_to_comfyui", side_effect=lambda path: Path(path).name), \
                    patch.object(video, "submit_task", side_effect=capture_submit), \
                    patch.object(video, "poll_result", return_value={"status": "pending"}), \
                    patch.object(video, "output_error"), \
                    patch.object(video, "output_result"), \
                    patch.object(sys, "argv", argv):
                video.main()
        return captured["workflow"]

    def test_i2v_two_images_use_native_first_last_frame(self):
        workflow = self._run_main("i2v", "img1,img2", model="hybrid", lora_strength="0.3")
        self.assertEqual(workflow["1"]["inputs"]["unet_name"],
                         "minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors")
        self.assertEqual(workflow["13"]["inputs"]["image"], "image_1.png")
        self.assertEqual(workflow["14"]["inputs"]["image"], "image_2.png")
        self.assertNotIn("100", workflow)
        self.assertEqual(workflow["70"]["inputs"]["strength_model"], 0.3)

    def test_i2v_multi_images_keep_hybrid_model_and_lora(self):
        workflow = self._run_main("i2v", "img1,img2,img3", model="hybrid", lora_strength="0.25")
        self.assertEqual(workflow["1"]["inputs"]["unet_name"],
                         "minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors")
        self.assertIn("100", workflow)
        self.assertEqual(workflow["70"]["inputs"]["strength_model"], 0.25)

    def test_ref_two_images_remain_two_reference_inputs(self):
        workflow = self._run_main("ref", "img1,img2", model="hybrid")
        inputs = workflow["7"]["inputs"]
        self.assertEqual(inputs["ref_images.ref_image_0"], ["15", 0])
        self.assertEqual(inputs["ref_images.ref_image_1"], ["16", 0])
        self.assertNotIn("first_frame", inputs)
        self.assertNotIn("last_frame", inputs)

    def test_latent_scale_requires_finite_value_between_one_and_four(self):
        workflow = video.load_workflow("h3_t2v_hybrid")
        for scale in (0.0, 4.1, float("nan"), float("inf")):
            with self.subTest(scale=scale), self.assertRaisesRegex(ValueError, "1-4"):
                video.apply_latent_upscale(workflow, 864, 480, "prompt", 5, scale)


class TestChainStateValidation(unittest.TestCase):
    def make_state(self, **overrides):
        state = {
            "version": 1,
            "run_id": "0123456789ab",
            "session_id": "session_test",
            "prompt": "prompt",
            "segments_total": 2,
            "segments_done": 0,
            "current_prompt_id": "prompt-1",
            "delivered": [],
            "width": 864,
            "height": 480,
            "seed": 1,
            "steps": 4,
            "noise": "on",
            "model": "hybrid",
            "no_lora": False,
            "legacy_sampler": False,
            "keep_audio": False,
            "uploaded_images": ["image.png"],
            "segment_lengths": [124, 124],
            "source_windows": None,
            "source_24_video": None,
            "source_original_video": None,
        }
        state.update(overrides)
        return state

    def test_rejects_missing_runtime_fields(self):
        state = self.make_state()
        del state["prompt"]
        with self.assertRaisesRegex(ValueError, "prompt"):
            chain._validate_state(json.dumps(state), "session_test")

    def test_rejects_empty_prompt_id_that_would_resubmit_segment(self):
        state = self.make_state(current_prompt_id="")
        with self.assertRaisesRegex(ValueError, "current_prompt_id"):
            chain._validate_state(json.dumps(state), "session_test")


if __name__ == "__main__":
    unittest.main()
