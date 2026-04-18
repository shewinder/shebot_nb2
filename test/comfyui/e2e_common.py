#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-04-17
Description: ComfyUI E2E 测试公共模块
Github: https://github.com/
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from unittest import TestCase, SkipTest

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

_SCRIPTS_DIR = _PROJECT_ROOT / "hoshino" / "modules" / "aichat" / "skills" / "image_generation" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from _common import http_get
from comfyui_workflow_loader import list_available_models
from comfyui import call_comfyui_generate, COMFYUI_BASE_URL

_RESULT_DIR = _PROJECT_ROOT / "data" / "test_output" / "e2e_results"
_RESULT_DIR.mkdir(parents=True, exist_ok=True)


def check_comfyui_online() -> bool:
    """检查 ComfyUI 服务是否在线"""
    base = COMFYUI_BASE_URL.rstrip("/")
    for endpoint in ["/system_stats", "/prompt", "/"]:
        result = http_get(f"{base}{endpoint}", timeout=5)
        if result.get("status") in (200, 405, 400):
            return True
    return False


def find_test_images(min_count: int = 2) -> List[str]:
    """查找可用于测试的真实图片（优先从 res/ 目录查找，该目录受版本控制）"""
    candidates: List[str] = []

    # 优先从 res/ 目录递归查找（受版本控制，更可靠）
    res_dir = _PROJECT_ROOT / "res"
    if res_dir.exists():
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
            for f in res_dir.rglob(ext):
                if f.stat().st_size > 1024:
                    candidates.append(str(f))
                if len(candidates) >= min_count * 2:
                    break
            if len(candidates) >= min_count * 2:
                break

    # 备选：data/aichat/images/（运行时生成，不一定存在）
    if len(candidates) < min_count:
        data_dir = _PROJECT_ROOT / "data" / "aichat" / "images"
        if data_dir.exists():
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                for f in data_dir.rglob(ext):
                    if f.stat().st_size > 1024:
                        candidates.append(str(f))
                    if len(candidates) >= min_count * 2:
                        break
                if len(candidates) >= min_count * 2:
                    break

    seen: set = set()
    unique: List[str] = []
    for p in candidates:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return unique[:max(min_count * 2, 4)]


def save_result(name: str, data: bytes, model: str, test_type: str) -> Path:
    """保存测试结果图片"""
    timestamp = datetime.now().strftime("%m%d_%H%M%S")
    filename = f"{test_type}_{model}_{timestamp}_{name}.png"
    filepath = _RESULT_DIR / filename
    filepath.write_bytes(data)
    return filepath


class BaseE2ETest(TestCase):
    """E2E 测试基类"""

    @classmethod
    def setUpClass(cls):
        cls.comfyui_online = check_comfyui_online()
        cls.test_images = find_test_images(min_count=2)
        cls.models = list_available_models()
        cls.report: Dict[str, Any] = {
            "script": cls.__name__,
            "start_time": datetime.now().isoformat(),
            "comfyui_base_url": COMFYUI_BASE_URL,
            "comfyui_online": cls.comfyui_online,
            "test_images_found": len(cls.test_images),
            "test_image_paths": cls.test_images,
            "results": []
        }

        if not cls.comfyui_online:
            raise SkipTest(f"ComfyUI 服务未在线（{COMFYUI_BASE_URL}），跳过 E2E 测试")

        print(f"\n{'='*50}")
        print(f"{cls.__name__}")
        print(f"ComfyUI: {COMFYUI_BASE_URL}")
        print(f"工作流: {len(cls.models)} 个")
        print(f"测试图: {len(cls.test_images)} 张")
        print(f"{'='*50}")

    @classmethod
    def tearDownClass(cls):
        cls.report["end_time"] = datetime.now().isoformat()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = _RESULT_DIR / f"report_{cls.__name__}_{timestamp}.json"
        filepath.write_text(json.dumps(cls.report, ensure_ascii=False, indent=2), encoding="utf-8")

        total = len(cls.report["results"])
        passed = sum(1 for r in cls.report["results"] if r["success"])
        print(f"\n{'='*50}")
        print(f"结果: {passed}/{total} 通过")
        print(f"报告: {filepath.name}")
        print(f"{'='*50}\n")

    def record(self, test_type: str, model: str, success: bool,
               duration: float, detail: str = "", filepath: str = "",
               error: str = "") -> None:
        """记录测试结果"""
        self.__class__.report["results"].append({
            "test_type": test_type,
            "model": model,
            "success": success,
            "duration_sec": round(duration, 2),
            "detail": detail,
            "result_image": filepath,
            "error": error,
            "timestamp": datetime.now().isoformat()
        })

    def run_generate(self, prompt: str, model_name: str, aspect_ratio: str = "",
                     image_paths: List[str] = None, test_type: str = "generate") -> tuple[bool, str]:
        """通用生成调用，自动记录结果

        Returns:
            (success, error_msg)
        """
        start = time.time()
        result = call_comfyui_generate(
            prompt,
            aspect_ratio=aspect_ratio,
            model_name=model_name,
            image_paths=image_paths
        )
        duration = time.time() - start

        if result.get("success"):
            img_path = save_result(test_type, result["data"], model_name, test_type)
            self.record(test_type, model_name, True, duration,
                        detail=f"成功 -> {img_path.name}",
                        filepath=str(img_path))
            print(f"  ✅ {model_name} ({duration:.1f}s) -> {img_path.name}")
            return True, ""
        else:
            error = result.get("error", "未知错误")
            self.record(test_type, model_name, False, duration, error=error)
            print(f"  ❌ {model_name} ({duration:.1f}s): {error}")
            return False, error
