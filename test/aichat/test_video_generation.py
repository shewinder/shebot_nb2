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

    def test_i2v_official_model_uses_shared_template(self):
        workflow = self._run_main("i2v", "img1", model="official")
        self.assertEqual(workflow["1"]["inputs"]["unet_name"],
                         "minimax_h3_fl2va_pruned_int8_convrot.safetensors")

    def test_ref_two_images_remain_two_reference_inputs(self):
        workflow = self._run_main("ref", "img1,img2", model="hybrid")
        inputs = workflow["7"]["inputs"]
        self.assertEqual(inputs["ref_images.ref_image_0"], ["15", 0])
        self.assertEqual(inputs["ref_images.ref_image_1"], ["16", 0])
        self.assertNotIn("first_frame", inputs)
        self.assertNotIn("last_frame", inputs)

    def test_latent_scale_requires_finite_value_between_one_and_four(self):
        workflow = video.load_workflow("h3_t2v")
        for scale in (0.0, 4.1, float("nan"), float("inf")):
            with self.subTest(scale=scale), self.assertRaisesRegex(ValueError, "1-4"):
                video.apply_latent_upscale(workflow, 864, 480, "prompt", 5, scale)


class TestChainStateValidation(unittest.TestCase):
    def make_state(self, **overrides):
        state = {
            "version": 2,
            "task": "ref",
            "run_id": "0123456789ab",
            "session_id": "session_test",
            "scenes": [
                {"prompt": "scene 1", "length": 124, "seed": 1},
                {"prompt": "scene 2", "length": 124, "seed": 2},
            ],
            "segments_total": 2,
            "segments_done": 0,
            "current_prompt_id": "prompt-1",
            "delivered": [],
            "width": 864,
            "height": 480,
            "steps": 4,
            "noise": "on",
            "model": "hybrid",
            "no_lora": False,
            "legacy_sampler": False,
            "keep_audio": False,
            "uploaded_images": ["image.png"],
            "source_windows": None,
            "source_24_video": None,
            "source_original_video": None,
        }
        state.update(overrides)
        return state

    def test_rejects_missing_runtime_fields(self):
        state = self.make_state()
        del state["scenes"]
        with self.assertRaisesRegex(ValueError, "scenes"):
            chain._validate_state(json.dumps(state), "session_test")

    def test_rejects_empty_prompt_id_that_would_resubmit_segment(self):
        state = self.make_state(current_prompt_id="")
        with self.assertRaisesRegex(ValueError, "current_prompt_id"):
            chain._validate_state(json.dumps(state), "session_test")

    def test_task_controls_image_requirements(self):
        state = self.make_state(task="t2v", uploaded_images=[])
        validated = chain._validate_state(json.dumps(state), "session_test")
        self.assertEqual(validated["task"], "t2v")
        state["uploaded_images"] = ["unexpected.png"]
        with self.assertRaisesRegex(ValueError, "t2v"):
            chain._validate_state(json.dumps(state), "session_test")

    def test_plan_has_per_scene_prompt_length_and_seed(self):
        scenes = chain._parse_plan(json.dumps([
            {"prompt": "first", "length": 124, "seed": 101},
            {"prompt": "second", "length": 141, "seed": 102},
        ]))
        self.assertEqual(scenes[1], {"prompt": "second", "length": 141, "seed": 102})

    def test_rejects_continuation_too_short_for_context(self):
        state = self.make_state()
        state["scenes"][1]["length"] = 22
        with self.assertRaisesRegex(ValueError, "上下文"):
            chain._validate_state(json.dumps(state), "session_test")

    def test_edit_scene_length_must_match_source_window(self):
        state = self.make_state(task="edit", source_windows=[[0, 124], [102, 107]],
                                source_24_video="source-24",
                                source_original_video="source-original")
        with self.assertRaisesRegex(ValueError, "长度不一致"):
            chain._validate_state(json.dumps(state), "session_test")


class TestChainWorkflow(unittest.TestCase):
    def make_state(self, task: str, images: list | None = None) -> dict:
        return {
            "version": 2,
            "task": task,
            "run_id": "0123456789ab",
            "session_id": "session_test",
            "scenes": [
                {"prompt": "first prompt", "length": 124, "seed": 101},
                {"prompt": "second prompt", "length": 124, "seed": 102},
            ],
            "segments_total": 2,
            "segments_done": 0,
            "current_prompt_id": None,
            "delivered": [],
            "width": 864,
            "height": 480,
            "steps": 4,
            "noise": "on",
            "model": "hybrid",
            "no_lora": False,
            "legacy_sampler": False,
            "keep_audio": False,
            "uploaded_images": images or [],
            "source_windows": None,
            "source_24_video": None,
            "source_original_video": None,
        }

    def build_initial(self, task: str, images: list | None = None) -> dict:
        return chain.build_segment_workflow(
            1, self.make_state(task, images), "ffmpeg", object(), Path("/tmp"))

    def assert_references_exist(self, workflow: dict) -> None:
        for node in workflow.values():
            for value in node.get("inputs", {}).values():
                if (isinstance(value, list) and len(value) == 2
                        and isinstance(value[0], str) and isinstance(value[1], int)):
                    self.assertIn(value[0], workflow)

    def test_t2v_initial_has_no_image_anchor_and_keeps_generated_audio(self):
        workflow = self.build_initial("t2v")
        self.assertEqual(workflow["20"]["class_type"], "MiniMaxH3ImageToVideo")
        self.assertNotIn("first_frame", workflow["20"]["inputs"])
        self.assertNotIn("last_frame", workflow["20"]["inputs"])
        self.assertEqual(workflow["19"]["class_type"], "VHS_VideoCombine")
        self.assertEqual(workflow["19"]["inputs"]["audio"], ["21", 0])
        self.assert_references_exist(workflow)

    def test_t2v_official_uses_shared_chain_template(self):
        state = self.make_state("t2v")
        state["model"] = "official"
        workflow = chain.build_segment_workflow(
            1, state, "ffmpeg", object(), Path("/tmp"))
        self.assertEqual(workflow["1"]["inputs"]["unet_name"],
                         "minimax_h3_fl2va_pruned_int8_convrot.safetensors")

    def test_i2v_initial_uses_first_frame_only(self):
        workflow = self.build_initial("i2v", ["first.png"])
        self.assertEqual(workflow["20"]["inputs"]["first_frame"], ["40", 0])
        self.assertNotIn("last_frame", workflow["20"]["inputs"])
        self.assert_references_exist(workflow)

    def test_ref_two_images_remain_reference_inputs(self):
        workflow = self.build_initial("ref", ["one.png", "two.png"])
        inputs = workflow["20"]["inputs"]
        self.assertEqual(inputs["ref_images.ref_image_0"], ["40", 0])
        self.assertEqual(inputs["ref_images.ref_image_1"], ["41", 0])
        self.assertEqual(workflow["19"]["inputs"]["audio"], ["21", 0])
        self.assert_references_exist(workflow)

    def test_fl2v_final_scene_uses_last_frame_and_audio_context(self):
        state = self.make_state("fl2v", ["first.png", "last.png"])
        state["segments_done"] = 1
        state["delivered"] = ["ai_video_1"]
        with patch.object(chain, "_state_video_path", return_value=Path("previous.mp4")), \
                patch.object(chain, "prepare_context"), \
                patch.object(chain, "upload_video_to_comfyui", return_value="context.mp4"):
            workflow = chain.build_segment_workflow(
                2, state, "ffmpeg", object(), Path("/tmp"))
        self.assertNotIn("first_frame", workflow["20"]["inputs"])
        self.assertEqual(workflow["20"]["inputs"]["last_frame"], ["41", 0])
        self.assertEqual(workflow["105"]["inputs"]["audio_vae"], ["4", 0])
        self.assertEqual(workflow["106"]["inputs"]["audio"], ["109", 0])
        self.assertEqual(workflow["108"]["inputs"]["audio"], ["106", 1])
        plan = json.loads(workflow["100"]["inputs"]["plan_json"])
        self.assertEqual(plan["shots"][0]["prompt"], "second prompt")
        self.assertEqual(plan["shots"][0]["seed"], 102)
        self.assert_references_exist(workflow)

    def test_edit_keeps_source_video_reference(self):
        state = self.make_state("edit", ["identity.png"])
        state.update({
            "source_windows": [[0, 124], [102, 124]],
            "source_24_video": "ai_video_source_24",
            "source_original_video": "user_video_source",
        })
        with patch.object(chain, "_state_video_path", return_value=Path("source.mp4")), \
                patch.object(chain, "slice_source_window"), \
                patch.object(chain, "upload_video_to_comfyui", return_value="source_slice.mp4"):
            workflow = chain.build_segment_workflow(
                1, state, "ffmpeg", object(), Path("/tmp"))
        self.assertEqual(workflow["20"]["class_type"], "MiniMaxH3ReferenceToVideo")
        self.assertEqual(workflow["20"]["inputs"]["ref_videos.ref_video_0"], ["49", 0])
        self.assertEqual(workflow["43"]["inputs"]["file"], "source_slice.mp4")
        self.assert_references_exist(workflow)

    def test_t2v_main_creates_v2_state(self):
        captured = {}
        plan = json.dumps([{"prompt": "scene", "length": 124, "seed": 101}])

        def capture_submit(state: dict, ffmpeg: str, store: object,
                           work_dir: Path) -> None:
            state["current_prompt_id"] = "prompt-test"

        def capture_state(state: dict, status: str, message: str,
                          error: str = "") -> None:
            captured.update({"state": state, "status": status, "error": error})

        argv = ["comfyui_video_chain.py", "--task", "t2v", "--plan-json", plan]
        with patch.object(chain, "find_ffmpeg", return_value="ffmpeg"), \
                patch.object(chain, "VideoStoreCore", return_value=object()), \
                patch.object(chain, "compute_size_for_aspect", return_value=(864, 480)), \
                patch.object(chain, "submit_next_segment", side_effect=capture_submit), \
                patch.object(chain, "output_state", side_effect=capture_state), \
                patch.object(sys, "argv", argv):
            chain.main()
        self.assertEqual(captured["status"], "partial")
        self.assertEqual(captured["state"]["version"], 2)
        self.assertEqual(captured["state"]["task"], "t2v")
        self.assertEqual(captured["state"]["scenes"][0]["seed"], 101)

    def test_edit_preparation_error_does_not_return_invalid_state(self):
        plan = json.dumps([{"prompt": "edit scene", "length": 124, "seed": 101}])
        argv = [
            "comfyui_video_chain.py", "--task", "edit", "--plan-json", plan,
            "--images", "image-1", "--source-video", "video-1",
        ]
        with patch.object(chain, "find_ffmpeg", return_value="ffmpeg"), \
                patch.object(chain, "VideoStoreCore", return_value=object()), \
                patch.object(chain, "resolve_image_file", return_value="image.png"), \
                patch.object(chain, "compute_target_size", return_value=(864, 480)), \
                patch.object(chain.shutil, "copy2"), \
                patch.object(chain, "upload_image_to_comfyui", return_value="image.png"), \
                patch.object(chain, "_state_video_path", side_effect=ValueError("missing")), \
                patch.object(chain, "output_error") as output_error, \
                patch.object(chain, "output_state") as output_state, \
                patch.object(sys, "argv", argv):
            chain.main()
        output_error.assert_called_once_with("missing")
        output_state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
