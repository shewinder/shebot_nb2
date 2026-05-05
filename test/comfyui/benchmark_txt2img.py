#!/usr/bin/env python3
"""
Author: SheBot
Date: 2026-04-19
Description: 文生图模型效果测试脚本
Github: https://github.com/

功能：
- 批量测试指定 ComfyUI 工作流（文生图模型）
- 覆盖动漫 / 真人两种风格，含安全内容与 NSFW 内容
- 脚本仅执行生成与保存，不做效果评判

运行方式：
    cd /root/bot/shebot_nb2
    COMFYUI_BASE_URL=http://127.0.0.1:8188 \
        .venv/bin/python test/comfyui/benchmark_txt2img.py --model sdxl_txt2img
"""
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

# ---------- 路径设置 ----------
_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

_SCRIPTS_DIR = (
    _PROJECT_ROOT
    / "hoshino"
    / "modules"
    / "aichat"
    / "aichat"
    / "skills"
    / "image_generation"
    / "scripts"
)
sys.path.insert(0, str(_SCRIPTS_DIR))
os.environ["PROJECT_ROOT"] = str(_PROJECT_ROOT)

from _common import http_get, http_post, store_image
from comfyui_workflow_loader import (
    load_workflow,
    apply_prompt,
    apply_size,
    list_available_models,
)

COMFYUI_BASE_URL = os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188")


# ---------- 测试用例 ----------
# 分类: anime / real
# 类型: safe / nsfw_light / nsfw
TEST_CASES: List[Dict[str, Any]] = [
    # ---- 动漫风格 ----
    {
        "name": "anime_safe",
        "category": "动漫",
        "type": "safe",
        "prompt": "1girl, solo, school uniform, cherry blossoms, smile, looking at viewer, soft lighting, masterpiece, best quality, detailed face",
        "aspect_ratio": "2:3",
    },
    {
        "name": "anime_nsfw_light",
        "category": "动漫",
        "type": "nsfw_light",
        "prompt": "1girl, solo, lingerie, bedroom, soft lighting, blush, looking at viewer, masterpiece, best quality, detailed skin",
        "aspect_ratio": "2:3",
    },
    {
        "name": "anime_nsfw",
        "category": "动漫",
        "type": "nsfw",
        "prompt": "1girl, solo, nude, lying on bed, detailed skin, soft lighting, blush, masterpiece, best quality",
        "aspect_ratio": "2:3",
    },
    {
        "name": "anime_genitalia",
        "category": "动漫",
        "type": "nsfw",
        "prompt": "1girl, solo, spread legs, pussy, detailed genitalia, close-up, soft lighting, masterpiece, best quality",
        "aspect_ratio": "1:1",
    },
    {
        "name": "anime_natural_lang",
        "category": "动漫",
        "type": "safe",
        "prompt": "A cute anime girl with long silver hair and purple eyes, wearing a cozy oversized sweater, sitting by a window on a rainy day, holding a warm cup of tea, soft indoor lighting, peaceful atmosphere",
        "aspect_ratio": "2:3",
    },
    {
        "name": "anime_chinese",
        "category": "动漫",
        "type": "safe",
        "prompt": "一个银发紫瞳的可爱动漫少女，穿着宽松的针织衫，坐在窗边听雨，手里捧着一杯热茶，柔和的室内光线，宁静的氛围",
        "aspect_ratio": "2:3",
    },
    # ---- 真人风格 ----
    {
        "name": "real_safe",
        "category": "真人",
        "type": "safe",
        "prompt": "a beautiful woman, professional portrait, natural makeup, soft studio lighting, elegant dress, looking at camera, photorealistic, 8k uhd",
        "aspect_ratio": "2:3",
    },
    {
        "name": "real_nsfw_light",
        "category": "真人",
        "type": "nsfw_light",
        "prompt": "a beautiful woman, bikini, beach, sunset, soft lighting, photorealistic, detailed skin, 8k uhd",
        "aspect_ratio": "2:3",
    },
    {
        "name": "real_nsfw",
        "category": "真人",
        "type": "nsfw",
        "prompt": "a beautiful woman, nude, lying on bed, soft lighting, detailed skin, photorealistic, 8k uhd",
        "aspect_ratio": "2:3",
    },
    {
        "name": "real_genitalia",
        "category": "真人",
        "type": "nsfw",
        "prompt": "a beautiful woman, spread legs, detailed pussy, close-up, soft lighting, photorealistic, 8k uhd",
        "aspect_ratio": "1:1",
    },
    {
        "name": "real_natural_lang",
        "category": "真人",
        "type": "safe",
        "prompt": "A young woman with natural makeup standing in a sunflower field during golden hour, wearing a flowing white dress, warm backlight creating a soft glow around her hair, photorealistic, cinematic composition",
        "aspect_ratio": "2:3",
    },
    {
        "name": "real_chinese",
        "category": "真人",
        "type": "safe",
        "prompt": "一位淡妆的年轻女子站在向日葵花田里，夕阳的余晖洒在她身上，穿着飘逸的白色长裙，温暖的逆光勾勒出她的发丝，真实感照片风格，电影级构图",
        "aspect_ratio": "2:3",
    },
    # ---- 二次元角色还原 ----
    {
        "name": "char_chino",
        "category": "角色",
        "type": "safe",
        "prompt": "kafuu chino, gochuumon wa usagi desu ka, blue hair, blue eyes, rabbit house uniform, smiling, looking at viewer, soft lighting, masterpiece, best quality",
        "aspect_ratio": "2:3",
    },
    {
        "name": "char_chino_nsfw",
        "category": "角色",
        "type": "nsfw",
        "prompt": "kafuu chino, gochuumon wa usagi desu ka, blue hair, blue eyes, nude, small breasts, lying on bed, detailed skin, soft lighting, blush, masterpiece, best quality",
        "aspect_ratio": "2:3",
    },
    {
        "name": "char_miku",
        "category": "角色",
        "type": "safe",
        "prompt": "hatsune miku, vocaloid, long turquoise twintails, black sleeves, necktie, headphones, singing, dynamic pose, stage lights, masterpiece, best quality",
        "aspect_ratio": "2:3",
    },
    {
        "name": "char_miku_nsfw",
        "category": "角色",
        "type": "nsfw",
        "prompt": "hatsune miku, vocaloid, long turquoise twintails, nude, medium breasts, detailed skin, soft lighting, blush, lying on bed, masterpiece, best quality",
        "aspect_ratio": "2:3",
    },
    {
        "name": "char_furina",
        "category": "角色",
        "type": "safe",
        "prompt": "furina de fontaine, genshin impact, short white hair with blue streaks, blue eyes, top hat, blue outfit, elegant pose, soft lighting, masterpiece, best quality",
        "aspect_ratio": "2:3",
    },
    {
        "name": "char_furina_nsfw",
        "category": "角色",
        "type": "nsfw",
        "prompt": "furina de fontaine, genshin impact, short white hair with blue streaks, blue eyes, nude, medium breasts, detailed skin, soft lighting, blush, lying on bed, masterpiece, best quality",
        "aspect_ratio": "2:3",
    },
]


def _call_generate(prompt: str, aspect_ratio: str, model_name: str) -> Dict[str, Any]:
    """调用 ComfyUI 生成，返回 {success, data|error}"""
    import copy

    import random

    base = COMFYUI_BASE_URL.rstrip("/")
    wf = copy.deepcopy(load_workflow(model_name))
    apply_prompt(wf, prompt)
    apply_size(wf, aspect_ratio)

    # 注入随机种子到所有 KSampler 节点（方案 B）
    for node in wf.values():
        if isinstance(node, dict) and node.get("class_type") == "KSampler":
            node.setdefault("inputs", {})
            node["inputs"]["seed"] = random.randint(0, 2**32 - 1)

    # 提交
    result = http_post(
        f"{base}/prompt",
        json_data={"prompt": wf, "client_id": "benchmark_txt2img"},
    )
    if "error" in result:
        return {"success": False, "error": result["error"]}
    if result.get("status", 0) not in (200,):
        return {
            "success": False,
            "error": f"HTTP {result.get('status')}: {result.get('text', '')[:200]}",
        }

    resp = result.get("json", {})
    prompt_id = resp.get("prompt_id")
    if not prompt_id:
        return {"success": False, "error": f"未返回 prompt_id: {resp}"}

    # 轮询
    history_url = f"{base}/history/{prompt_id}"
    timeout = 300
    interval = 2
    elapsed = 0

    while elapsed < timeout:
        time.sleep(interval)
        elapsed += interval
        hist = http_get(history_url)
        if "error" in hist:
            continue
        data = hist.get("json", {})
        if not isinstance(data, dict):
            continue
        entry = data.get(prompt_id, {})
        outputs = entry.get("outputs", {})
        for node_id, node_out in outputs.items():
            for img_info in node_out.get("images", []):
                filename = img_info.get("filename")
                if not filename:
                    continue
                from urllib.parse import quote

                view_url = (
                    f"{base}/view?filename={quote(filename)}"
                    f"&subfolder={quote(img_info.get('subfolder', ''))}"
                    f"&type={quote(img_info.get('type', 'output'))}"
                )
                img_resp = http_get(view_url)
                if img_resp.get("status") == 200:
                    content = img_resp.get("content")
                    if content:
                        return {"success": True, "data": content}
                    return {"success": False, "error": "/view 未返回图片数据"}

    return {"success": False, "error": "生成超时"}


def _should_run(case: Dict[str, Any], nsfw_only: bool, category_modes: List[str]) -> bool:
    """根据 NSFW 开关和 category 过滤决定是否执行该用例"""
    # NSFW 过滤（nsfw_light 与 nsfw 统一视为 nsfw）
    type_ok = True
    if nsfw_only and case["type"] not in ("nsfw_light", "nsfw"):
        type_ok = False

    # category 过滤
    cat_ok = False
    if "all" in category_modes:
        cat_ok = True
    elif case["category"] in category_modes:
        cat_ok = True

    return type_ok and cat_ok


def run_benchmark(model_name: str, output_dir: Path, nsfw_only: bool = False, category_modes: List[str] = None) -> None:
    """执行完整测试套件"""
    if category_modes is None:
        category_modes = ["all"]
    available = list_available_models()
    if model_name not in available:
        print(f"[ERROR] 模型 '{model_name}' 不在可用列表中: {available}")
        sys.exit(1)

    cases = [c for c in TEST_CASES if _should_run(c, nsfw_only, category_modes)]
    if not cases:
        print(f"[ERROR] 过滤条件 nsfw_only={nsfw_only} category={category_modes} 下无匹配用例")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"模型: {model_name}")
    print(f"模式: {'仅NSFW' if nsfw_only else '全部'}")
    print(f"category过滤: {', '.join(category_modes)}")
    print(f"用例数: {len(cases)}/{len(TEST_CASES)}")
    print(f"输出目录: {output_dir}")
    print(f"ComfyUI: {COMFYUI_BASE_URL}")
    print(f"开始时间: {datetime.now().isoformat()}")
    print("-" * 60)

    results: List[Dict[str, Any]] = []

    for case in cases:
        print(f"[{case['category']}/{case['type']}] {case['name']} ... ", end="", flush=True)
        start = time.time()
        result = _call_generate(case["prompt"], case["aspect_ratio"], model_name)
        elapsed = time.time() - start

        if result["success"]:
            # 保存到输出目录（不经过 store_image，直接写文件便于查看）
            out_path = output_dir / f"{case['name']}.png"
            out_path.write_bytes(result["data"])
            size_kb = len(result["data"]) / 1024
            print(f"OK  ({elapsed:.1f}s, {size_kb:.1f}KB) -> {out_path.name}")
            results.append(
                {
                    "name": case["name"],
                    "category": case["category"],
                    "type": case["type"],
                    "status": "OK",
                    "time": elapsed,
                    "file": out_path.name,
                }
            )
        else:
            print(f"FAIL ({elapsed:.1f}s) -> {result['error']}")
            results.append(
                {
                    "name": case["name"],
                    "category": case["category"],
                    "type": case["type"],
                    "status": "FAIL",
                    "time": elapsed,
                    "error": result["error"],
                }
            )

    # 汇总报告
    print("-" * 60)
    ok_count = sum(1 for r in results if r["status"] == "OK")
    fail_count = len(results) - ok_count
    print(f"完成: {ok_count}/{len(results)} 成功, {fail_count} 失败")
    print()
    print("按分类统计:")
    cats = sorted({r["category"] for r in results})
    for cat in cats:
        cat_results = [r for r in results if r["category"] == cat]
        if not cat_results:
            continue
        cat_ok = sum(1 for r in cat_results if r["status"] == "OK")
        print(f"  {cat}: {cat_ok}/{len(cat_results)} 成功")
    print()
    print("按类型统计:")
    for typ in ("safe", "nsfw_light", "nsfw"):
        typ_results = [r for r in results if r["type"] == typ]
        if not typ_results:
            continue
        typ_ok = sum(1 for r in typ_results if r["status"] == "OK")
        print(f"  {typ}: {typ_ok}/{len(typ_results)} 成功")
    print()
    print(f"结束时间: {datetime.now().isoformat()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="文生图模型效果测试")
    parser.add_argument(
        "--model",
        default="",
        help="ComfyUI 工作流模型名（对应 reference/ 下的 .json 文件名）",
    )
    parser.add_argument(
        "--output",
        default=str(_PROJECT_ROOT / "test_output" / "comfyui_benchmark"),
        help="输出目录基准路径（默认: test_output/comfyui_benchmark）",
    )
    parser.add_argument(
        "--nsfw",
        action="store_true",
        help="仅测试 NSFW 内容（含 nsfw_light），默认测试全部",
    )
    parser.add_argument(
        "--category",
        choices=["all", "动漫", "真人", "角色"],
        default=["all"],
        nargs="+",
        help="按分类过滤，可指定多个（空格分隔）。all=全部, 动漫=动漫风格, 真人=真人风格, 角色=二次元角色还原。例: --category 角色",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有可用模型后退出",
    )
    args = parser.parse_args()

    if args.list:
        print("可用模型:")
        for m in list_available_models():
            print(f"  - {m}")
        sys.exit(0)

    if not args.model:
        print("[ERROR] --model 参数必填（或用 --list 查看可用模型）")
        sys.exit(1)

    output_dir = Path(args.output) / args.model
    run_benchmark(args.model, output_dir, nsfw_only=args.nsfw, category_modes=args.category)


if __name__ == "__main__":
    main()
