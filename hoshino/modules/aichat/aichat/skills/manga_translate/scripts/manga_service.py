"""manga_translate GPU 服务调用脚本

用法:
  python manga_service.py ocr --image <identifier>
  python manga_service.py inpaint_render --image <identifier> --data-id <id> --translations '<JSON>'
"""
import argparse
import base64
import json
import os
from pathlib import Path
from typing import Optional

import requests

GPU_SERVICE = os.environ.get("MANGA_GPU_SERVICE", "http://localhost:8899")

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
    images = json.loads(os.environ.get("SKILL_IMAGES", "{}"))
    key = identifier if identifier.startswith("<") else f"<{identifier}>"
    return images.get(key)


def output_result(success: bool, **kwargs):
    print(json.dumps({"success": success, **kwargs}, ensure_ascii=False))


def cmd_ocr(args):
    """检测并识别文字"""
    img_path = resolve_image(args.image)
    if not img_path:
        output_result(False, error=f"图像 {args.image} 未找到")
        return

    with open(img_path, "rb") as f:
        r = requests.post(f"{GPU_SERVICE}/ocr",
                          files={"file": (os.path.basename(img_path), f, "image/png")},
                          timeout=300)
    if r.status_code != 200:
        output_result(False, error=f"OCR 服务返回 {r.status_code}")
        return

    data = r.json()
    output_result(True, results=data["results"], data_id=data.get("data_id", ""))


def cmd_inpaint_render(args):
    """擦除 + 嵌字"""
    img_path = resolve_image(args.image)
    if not img_path:
        output_result(False, error=f"图像 {args.image} 未找到")
        return

    if not args.translations:
        output_result(False, error="需要 --translations")
        return

    # 校验 JSON 格式
    try:
        translations = json.loads(args.translations)
    except json.JSONDecodeError as e:
        output_result(False, error=f"translations JSON 格式错误: {e}")
        return

    if not isinstance(translations, list) or not translations:
        output_result(False, error="translations 必须是非空数组")
        return

    data = {"translations": args.translations}
    if args.data_id:
        data["data_id"] = args.data_id

    with open(img_path, "rb") as f:
        r = requests.post(f"{GPU_SERVICE}/inpaint_and_render",
                          files={"file": (os.path.basename(img_path), f, "image/png")},
                          data=data,
                          timeout=300)

    if r.status_code != 200:
        output_result(False, error=f"GPU 服务返回 {r.status_code}: {r.text[:200]}")
        return

    data = r.json()
    img_bytes = base64.b64decode(data["rendered_image"])

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
        out_path = Path("/tmp") / f"manga_translated_{session_id}.png"
        out_path.write_bytes(img_bytes)
        output_result(True, path=str(out_path))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("ocr")
    p.add_argument("--image", required=True)
    p.set_defaults(func=cmd_ocr)

    p = sub.add_parser("inpaint_render")
    p.add_argument("--image", required=True)
    p.add_argument("--translations", default="")
    p.add_argument("--data-id", default="")
    p.set_defaults(func=cmd_inpaint_render)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
