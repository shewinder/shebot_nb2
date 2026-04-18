#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-04-17
Description: E2E 测试 - qwen_image_edit 系列工作流
Github: https://github.com/

验证场景：
- qwen_image_edit_single: 单图编辑
- qwen_image_edit: 多图编辑/融合（2张输入图）
"""
import unittest
from pathlib import Path

from e2e_common import BaseE2ETest

TEST_PROMPT_SINGLE = "把图中的女孩换成赛博朋克风格"
TEST_PROMPT_MULTI = "把图一右边的女孩换成图二的女孩"


class TestE2EQwenImageEditSingle(BaseE2ETest):
    """qwen_image_edit_single 端到端测试"""

    def test_edit_single_image(self):
        """单图编辑"""
        if not self.test_images:
            self.skipTest("无可用测试图片")

        img = self.test_images[0]
        print(f"[qwen_image_edit_single] 单图编辑 | 输入: {Path(img).name}")

        ok, error = self.run_generate(
            TEST_PROMPT_SINGLE,
            "qwen_image_edit_single",
            aspect_ratio="1:1",
            image_paths=[img],
            test_type="edit_single"
        )
        if not ok:
            self.fail(f"单图编辑失败: {error}")


class TestE2EQwenImageEditMulti(BaseE2ETest):
    """qwen_image_edit 端到端测试"""

    def test_edit_multi_images(self):
        """多图编辑（2张输入图）"""
        if len(self.test_images) >= 2:
            images = self.test_images[:2]
        elif len(self.test_images) == 1:
            images = self.test_images[:1] * 2
            print("[提示] 仅找到 1 张图，复制为第二张")
        else:
            self.skipTest("无可用测试图片")

        img_names = [Path(p).name for p in images]
        print(f"[qwen_image_edit] 多图编辑 | 输入: {', '.join(img_names)}")

        ok, error = self.run_generate(
            TEST_PROMPT_MULTI,
            "qwen_image_edit",
            aspect_ratio="1:1",
            image_paths=images,
            test_type="edit_multi"
        )
        if not ok:
            self.fail(f"多图编辑失败: {error}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
