"""manga_translate GPU 服务调用脚本

用法:
  python manga_service.py detect --image <identifier>
  python manga_service.py inpaint_render --image <identifier> --translations '<JSON>'
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests

# GPU 服务地址（可通过环境变量覆盖）
GPU_SERVICE = os.environ.get("MANGA_GPU_SERVICE", "http://localhost:8899")

# ImageStoreCore 动态加载（避免依赖 hoshino）
_project_root = Path(os.environ.get("PROJECT_ROOT", "."))
_core_path = _project_root / "hoshino" / "modules" / "aichat" / "aichat" / "_image_store_core.py"

def _load_image_store():
    if _core_path.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location("_image_store_core", str(_core_path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.ImageStoreCore
    return None


def resolve_image(identifier: str) -> Optional[str]:
    """从 SKILL_IMAGES 环境变量解析图像路径"""
    images = json.loads(os.environ.get("SKILL_IMAGES", "{}"))
    key = identifier if identifier.startswith("<") else f"<{identifier}>"
    return images.get(key)


def output_result(success: bool, **kwargs):
    print(json.dumps({"success": success, **kwargs}, ensure_ascii=False))


def cmd_ocr(args):
    """本地 OCR 识别文字"""
    identifier = args.image
    img_path = resolve_image(identifier)
    if not img_path:
        output_result(False, error=f"图像 {identifier} 未找到")
        return

    # 读取 bboxes
    bboxes_str = args.bboxes or ""
    if args.bboxes_file:
        bf = Path(args.bboxes_file)
        if not bf.is_absolute():
            bf = Path(_project_root) / bf
        bboxes_str = bf.read_text()
    elif bboxes_str and Path(bboxes_str).exists():
        bboxes_str = Path(bboxes_str).read_text()

    if not bboxes_str:
        output_result(False, error="需要 --bboxes 或 --bboxes-file")
        return

    with open(img_path, "rb") as f:
        r = requests.post(f"{GPU_SERVICE}/ocr",
                          files={"file": (os.path.basename(img_path), f, "image/png")},
                          data={"bboxes": bboxes_str},
                          timeout=300)
    if r.status_code != 200:
        output_result(False, error=f"OCR 服务返回 {r.status_code}")
        return

    data = r.json()
    output_result(True, results=data["results"])


def cmd_detect(args):
    """CRAFT 文字检测"""
    identifier = args.image
    img_path = resolve_image(identifier)
    if not img_path:
        output_result(False, error=f"图像 {identifier} 未找到")
        return

    with open(img_path, "rb") as f:
        r = requests.post(f"{GPU_SERVICE}/detect",
                          files={"file": (os.path.basename(img_path), f, "image/png")},
                          timeout=300)

    if r.status_code != 200:
        output_result(False, error=f"GPU 服务返回 {r.status_code}")
        return

    data = r.json()
    output_result(True, bboxes=data["bboxes"])


def cmd_inpaint_render(args):
    """擦除 + 嵌字"""
    identifier = args.image

    img_path = resolve_image(identifier)
    if not img_path:
        output_result(False, error=f"图像 {identifier} 未找到")
        return

    # 优先读文件（避免命令行参数转义问题）
    if args.translations_file:
        file_path = Path(args.translations_file)
        if not file_path.is_absolute():
            file_path = Path(_project_root) / file_path
        try:
            translations_str = file_path.read_text()
        except Exception as e:
            output_result(False, error=f"读取 translations 文件失败: {file_path}: {e}")
            return
    elif args.translations:
        translations_str = args.translations
    else:
        output_result(False, error="需要 --translations 或 --translations-file")
        return

    # 解析并校验 translations
    try:
        translations = json.loads(translations_str)
    except json.JSONDecodeError as e:
        output_result(False, error=f"translations JSON 格式错误: {e}")
        return

    if not isinstance(translations, list) or not translations:
        output_result(False, error="translations 必须是非空数组")
        return

    # 传递 bbox 坐标（避免服务端重复检测）
    data = {"translations": translations_str}

    # 优先读文件
    bboxes_str = args.bboxes or ""
    if args.bboxes_file:
        bf = Path(args.bboxes_file)
        if not bf.is_absolute():
            bf = Path(_project_root) / bf
        bboxes_str = bf.read_text()
    elif bboxes_str and Path(bboxes_str).exists():
        bboxes_str = Path(bboxes_str).read_text()

    if bboxes_str:
        data["bboxes"] = bboxes_str

    with open(img_path, "rb") as f:
        r = requests.post(f"{GPU_SERVICE}/inpaint_and_render",
                          files={"file": (os.path.basename(img_path), f, "image/png")},
                          data=data,
                          timeout=300)

    if r.status_code != 200:
        output_result(False, error=f"GPU 服务返回 {r.status_code}: {r.text[:200]}")
        return

    data = r.json()
    import base64
    img_bytes = base64.b64decode(data["rendered_image"])

    # 存储结果到 ImageStore
    session_id = os.environ.get("SESSION_ID", "unknown")
    ImageStoreCore = _load_image_store()
    if ImageStoreCore:
        store = ImageStoreCore(session_id)
        entry = store.store_bytes(img_bytes, source="ai", ext="png")
        output_result(True, identifier=entry.identifier,
                      path=str(entry.file_path),
                      format=entry.format,
                      width=entry.width,
                      height=entry.height)
    else:
        # 无 ImageStore，直接保存到临时文件
        out_path = Path("/tmp") / f"manga_translated_{session_id}.png"
        out_path.write_bytes(img_bytes)
        output_result(True, path=str(out_path))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)

    p_ocr = sub.add_parser("ocr")
    p_ocr.add_argument("--image", required=True)
    p_ocr.add_argument("--bboxes", default="")
    p_ocr.add_argument("--bboxes-file", default="")
    p_ocr.set_defaults(func=cmd_ocr)

    p_detect = sub.add_parser("detect")
    p_detect.add_argument("--image", required=True)
    p_detect.set_defaults(func=cmd_detect)

    p_render = sub.add_parser("inpaint_render")
    p_render.add_argument("--image", required=True)
    p_render.add_argument("--translations", default="")
    p_render.add_argument("--translations-file", default="")
    p_render.add_argument("--bboxes", default="")
    p_render.add_argument("--bboxes-file", default="")
    p_render.set_defaults(func=cmd_inpaint_render)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
