#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-04-17
Description: ComfyUI 多工作流架构测试脚本
Github: https://github.com/

运行方式:
    cd /root/bot/shebot_nb2
    .venv/bin/python test/comfyui/test_comfyui_workflows.py
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# ---------- 加载环境变量 ----------
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

# ---------- 路径设置 ----------
_SCRIPTS_DIR = _PROJECT_ROOT / "hoshino" / "modules" / "aichat" / "skills" / "image_generation" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

# 设置 PROJECT_ROOT 环境变量（供 loader 使用）
os.environ["PROJECT_ROOT"] = str(_PROJECT_ROOT)

from comfyui_workflow_loader import (
    load_workflow,
    apply_prompt, apply_input_images, apply_size,
    list_available_models,
    _SIZE_MAP,
)
from comfyui import (
    call_comfyui_generate,
    COMFYUI_BASE_URL,
    upload_image_to_comfyui,
)


class TestListAvailableModels(unittest.TestCase):
    """模型列表扫描测试"""

    def test_lists_existing_models(self):
        """应列出 reference/ 目录下的所有模型"""
        models = list_available_models()
        self.assertIn("z_image_turbo", models)
        self.assertIn("qwen_image_edit", models)

    def test_returns_sorted_list(self):
        """返回的列表应已排序"""
        models = list_available_models()
        self.assertEqual(models, sorted(models))


class TestLoadWorkflow(unittest.TestCase):
    """工作流加载测试"""

    def test_load_existing(self):
        """加载存在的工作流"""
        wf = load_workflow("z_image_turbo")
        self.assertIn("57:27", wf)
        self.assertEqual(wf["57:27"]["inputs"]["text"], "{{prompt}}")

    def test_load_qwen_edit(self):
        """加载 qwen_image_edit 工作流"""
        wf = load_workflow("qwen_image_edit")
        self.assertIn("78", wf)
        self.assertEqual(wf["78"]["inputs"]["image"], "{{input_image_1}}")

    def test_load_not_found(self):
        """加载不存在的工作流应抛出异常"""
        with self.assertRaises(RuntimeError) as ctx:
            load_workflow("not_exist")
        self.assertIn("未找到工作流", str(ctx.exception))
        self.assertIn("z_image_turbo", str(ctx.exception))


class TestPlaceholderReplacement(unittest.TestCase):
    """占位符替换测试"""

    def setUp(self):
        self.workflow = {
            "10": {
                "inputs": {"text": "{{prompt}}", "clip": ["11", 0]},
                "class_type": "CLIPTextEncode"
            },
            "20": {
                "inputs": {"image": "{{input_image}}"},
                "class_type": "LoadImage"
            },
            "21": {
                "inputs": {"image": "{{input_image_1}}"},
                "class_type": "LoadImage"
            },
            "22": {
                "inputs": {"image": "{{input_image_2}}"},
                "class_type": "LoadImage"
            },
            "30": {
                "inputs": {"width": 512, "height": 512, "batch_size": 1},
                "class_type": "EmptyLatentImage"
            }
        }

    def test_apply_prompt(self):
        """替换 {{prompt}} 占位符"""
        apply_prompt(self.workflow, "一只可爱的猫")
        self.assertEqual(self.workflow["10"]["inputs"]["text"], "一只可爱的猫")

    def test_apply_input_image(self):
        """替换 {{input_image}} 占位符"""
        apply_input_images(self.workflow, ["uploaded_123.png"])
        self.assertEqual(self.workflow["20"]["inputs"]["image"], "uploaded_123.png")

    def test_apply_input_images_single(self):
        """apply_input_images 单图模式"""
        apply_input_images(self.workflow, ["single.png"])
        self.assertEqual(self.workflow["20"]["inputs"]["image"], "single.png")
        self.assertEqual(self.workflow["21"]["inputs"]["image"], "single.png")

    def test_apply_input_images_multi(self):
        """apply_input_images 多图模式"""
        apply_input_images(self.workflow, ["img_a.png", "img_b.png"])
        self.assertEqual(self.workflow["20"]["inputs"]["image"], "img_a.png")
        self.assertEqual(self.workflow["21"]["inputs"]["image"], "img_a.png")
        self.assertEqual(self.workflow["22"]["inputs"]["image"], "img_b.png")

    def test_apply_input_images_empty(self):
        """apply_input_images 空列表不报错"""
        original = self.workflow["20"]["inputs"]["image"]
        apply_input_images(self.workflow, [])
        self.assertEqual(self.workflow["20"]["inputs"]["image"], original)

    def test_apply_prompt_nested(self):
        """在嵌套结构中也能正确替换"""
        self.workflow["40"] = {
            "inputs": {"settings": [{"text": "{{prompt}}"}]}
        }
        apply_prompt(self.workflow, "测试")
        self.assertEqual(self.workflow["40"]["inputs"]["settings"][0]["text"], "测试")


class TestSizeAdjustment(unittest.TestCase):
    """尺寸调整测试"""

    def setUp(self):
        self.workflow = {
            "10": {
                "inputs": {"width": 512, "height": 512, "batch_size": 1},
                "class_type": "EmptyLatentImage"
            }
        }

    def test_apply_size_1_1(self):
        """1:1 比例"""
        apply_size(self.workflow, "1:1")
        self.assertEqual(self.workflow["10"]["inputs"]["width"], 1024)
        self.assertEqual(self.workflow["10"]["inputs"]["height"], 1024)

    def test_apply_size_16_9(self):
        """16:9 比例"""
        apply_size(self.workflow, "16:9")
        self.assertEqual(self.workflow["10"]["inputs"]["width"], 1536)
        self.assertEqual(self.workflow["10"]["inputs"]["height"], 864)

    def test_apply_size_empty(self):
        """空字符串使用默认尺寸"""
        apply_size(self.workflow, "")
        self.assertEqual(self.workflow["10"]["inputs"]["width"], 1024)
        self.assertEqual(self.workflow["10"]["inputs"]["height"], 1536)

    def test_apply_size_invalid(self):
        """非法比例回退到默认"""
        apply_size(self.workflow, "999:1")
        self.assertEqual(self.workflow["10"]["inputs"]["width"], 1024)
        self.assertEqual(self.workflow["10"]["inputs"]["height"], 1536)

    def test_apply_size_multiple_latent_nodes(self):
        """只修改第一个 latent 节点"""
        self.workflow["20"] = {
            "inputs": {"width": 256, "height": 256},
            "class_type": "EmptySD3LatentImage"
        }
        apply_size(self.workflow, "1:1")
        self.assertEqual(self.workflow["10"]["inputs"]["width"], 1024)
        self.assertEqual(self.workflow["20"]["inputs"]["width"], 256)


class TestComfyuiIntegration(unittest.TestCase):
    """comfyui.py 集成测试（mock HTTP）"""

    def test_load_workflow_success(self):
        """成功获取工作流 JSON"""
        wf = load_workflow("z_image_turbo")
        self.assertIn("57:27", wf)
        self.assertEqual(wf["57:27"]["inputs"]["text"], "{{prompt}}")

    def test_parse_args(self):
        """CLI 参数解析"""
        import comfyui as cu
        test_argv = [
            "comfyui.py",
            "--prompt", "一只猫",
            "--model", "z_image_turbo",
            "--aspect-ratio", "1:1",
            "--images", "img1,img2"
        ]
        with patch.object(sys, "argv", test_argv):
            args = cu._parse_args()
            self.assertEqual(args.prompt, "一只猫")
            self.assertEqual(args.model, "z_image_turbo")
            self.assertEqual(args.aspect_ratio, "1:1")
            self.assertEqual(args.images, "img1,img2")

    @patch("comfyui.http_post")
    @patch("comfyui.http_get")
    def test_call_comfyui_generate_success(self, mock_get, mock_post):
        """模拟完整的 ComfyUI 生成流程"""
        mock_post.return_value = {
            "status": 200,
            "json": {"prompt_id": "test-prompt-123"}
        }

        def mock_get_side_effect(url, **kwargs):
            if "/history/" in url:
                return {
                    "status": 200,
                    "json": {
                        "test-prompt-123": {
                            "outputs": {
                                "9": {
                                    "images": [
                                        {"filename": "test.png", "subfolder": "", "type": "output"}
                                    ]
                                }
                            }
                        }
                    }
                }
            elif "/view?" in url:
                return {"status": 200, "content": b"fake_image_data"}
            return {"status": 404}

        mock_get.side_effect = mock_get_side_effect

        result = call_comfyui_generate(
            "一只猫", aspect_ratio="1:1", model_name="z_image_turbo"
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"], b"fake_image_data")

    @patch("comfyui.http_post")
    def test_upload_image_to_comfyui(self, mock_post):
        """测试图片上传到 ComfyUI"""
        mock_post.return_value = {
            "status": 200,
            "json": {"name": "uploaded_abc.png", "subfolder": ""}
        }

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake_png_data")
            temp_path = f.name

        try:
            filename = upload_image_to_comfyui(temp_path)
            self.assertEqual(filename, "uploaded_abc.png")
        finally:
            os.unlink(temp_path)

    @patch("comfyui.http_post")
    def test_upload_image_failure(self, mock_post):
        """上传图片失败时应抛出异常"""
        mock_post.return_value = {"error": "Connection refused"}

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake_png_data")
            temp_path = f.name

        try:
            with self.assertRaises(RuntimeError) as ctx:
                upload_image_to_comfyui(temp_path)
            self.assertIn("上传图片到 ComfyUI 失败", str(ctx.exception))
        finally:
            os.unlink(temp_path)


class TestSizeMap(unittest.TestCase):
    """尺寸映射表测试"""

    def test_all_ratios_have_valid_dimensions(self):
        """所有比例映射都有正整数尺寸"""
        for ratio, size in _SIZE_MAP.items():
            with self.subTest(ratio=ratio):
                self.assertIsInstance(size["width"], int)
                self.assertIsInstance(size["height"], int)
                self.assertGreater(size["width"], 0)
                self.assertGreater(size["height"], 0)


class TestBuiltinWorkflow(unittest.TestCase):
    """内置默认工作流测试"""

    def test_z_image_turbo_structure(self):
        """z_image_turbo 工作流结构完整"""
        wf = load_workflow("z_image_turbo")

        required_nodes = {
            "SaveImage",
            "CLIPLoader",
            "VAELoader",
            "UNETLoader",
            "CLIPTextEncode",
            "EmptySD3LatentImage",
            "KSampler",
        }
        found_classes = {node["class_type"] for node in wf.values() if isinstance(node, dict)}
        for cls in required_nodes:
            self.assertIn(cls, found_classes, f"缺少 {cls} 节点")

        for node in wf.values():
            if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode":
                self.assertEqual(node["inputs"]["text"], "{{prompt}}")
                break
        else:
            self.fail("未找到 CLIPTextEncode 节点")

    def test_qwen_image_edit_structure(self):
        """qwen_image_edit 工作流结构完整"""
        wf = load_workflow("qwen_image_edit")

        # 检查关键节点
        found_classes = {node["class_type"] for node in wf.values() if isinstance(node, dict)}
        self.assertIn("SaveImage", found_classes)
        self.assertIn("LoadImage", found_classes)
        self.assertIn("TextEncodeQwenImageEditPlus", found_classes)
        self.assertIn("KSampler", found_classes)

        # 检查占位符
        wf_str = json.dumps(wf)
        self.assertIn("{{prompt}}", wf_str)
        self.assertIn("{{input_image_1}}", wf_str)
        self.assertIn("{{input_image_2}}", wf_str)


class TestComfyuiMainFlow(unittest.TestCase):
    """comfyui.py main() 主流程测试"""

    @patch("comfyui.call_comfyui_generate")
    @patch("comfyui.output_result")
    def test_main_generate_only(self, mock_output, mock_call):
        """纯文生图主流程"""
        mock_call.return_value = {"success": True, "data": b"fake_image"}

        import comfyui as cu
        test_argv = [
            "comfyui.py",
            "--prompt", "一只猫",
            "--model", "z_image_turbo",
            "--aspect-ratio", "1:1"
        ]
        with patch.object(sys, "argv", test_argv):
            cu.main()

        mock_call.assert_called_once_with(
            "一只猫",
            aspect_ratio="1:1",
            model_name="z_image_turbo",
            image_paths=None
        )
        mock_output.assert_called_once()
        pos_args, kw_args = mock_output.call_args
        self.assertTrue(pos_args[0])
        self.assertEqual(kw_args["model"], "z_image_turbo")

    @patch("comfyui.output_error")
    def test_main_missing_model(self, mock_error):
        """缺少 --model 参数"""
        import comfyui as cu
        test_argv = ["comfyui.py", "--prompt", "一只猫"]
        with patch.object(sys, "argv", test_argv):
            cu.main()
        mock_error.assert_called_once_with("--model 参数必填")


if __name__ == "__main__":
    unittest.main(verbosity=2)
