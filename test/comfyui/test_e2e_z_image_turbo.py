#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-04-17
Description: E2E 测试 - z_image_turbo 工作流
Github: https://github.com/

验证场景：
- 文生图
- 不同尺寸比例
"""
import unittest

from e2e_common import BaseE2ETest

TEST_PROMPT = "一只可爱的橘猫在樱花树下睡觉，粉色花瓣飘落，治愈系画风"


class TestE2EZImageTurbo(BaseE2ETest):
    """z_image_turbo 端到端测试"""

    def test_generate(self):
        """文生图"""
        print("[z_image_turbo] 文生图")
        ok, error = self.run_generate(TEST_PROMPT, "z_image_turbo", aspect_ratio="1:1")
        if not ok:
            self.fail(f"文生图失败: {error}")

    def test_ratio_1_1(self):
        """比例 1:1"""
        print("[z_image_turbo] 比例 1:1")
        ok, error = self.run_generate(
            f"{TEST_PROMPT}，比例1:1",
            "z_image_turbo",
            aspect_ratio="1:1",
            test_type="ratio_1:1"
        )
        if not ok:
            self.fail(f"比例 1:1 失败: {error}")

    def test_ratio_9_16(self):
        """比例 9:16"""
        print("[z_image_turbo] 比例 9:16")
        ok, error = self.run_generate(
            f"{TEST_PROMPT}，比例9:16",
            "z_image_turbo",
            aspect_ratio="9:16",
            test_type="ratio_9:16"
        )
        if not ok:
            self.fail(f"比例 9:16 失败: {error}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
