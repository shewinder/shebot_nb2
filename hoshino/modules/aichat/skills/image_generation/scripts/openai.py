#!/usr/bin/env python3
"""
OpenAI DALL-E 图像生成/编辑脚本

支持：
- 文生图（/images/generations）
- 图生图/编辑（/images/edits，multipart form）
- size 参数映射到 OpenAI 标准尺寸

注意：prompt 已由 AI 按模型调优策略处理，脚本原样透传，不做任何修改。
"""
import base64
import io
import os
import sys
from pathlib import Path

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

sys.path.insert(0, str(Path(__file__).parent))
from _common import (
    get_image_paths, resolve_image_file,
    store_image, read_image_file, http_post,
    output_result, output_error, parse_args
)


def _map_size(size: str) -> str:
    """将通用 size 映射到 OpenAI 标准尺寸"""
    mapping = {
        "512": "1024x1024",
        "1K": "1024x1024",
        "2K": "1536x1024",
        "4K": "1536x1536",
    }
    return mapping.get(size, "1024x1024")


def _get_closest_size(width: int, height: int) -> str:
    """根据原图比例选择最接近的 OpenAI 尺寸"""
    ratio = width / height
    if ratio >= 1.3:
        return "1536x1024"
    elif ratio <= 0.7:
        return "1024x1536"
    return "1024x1024"


def _convert_to_png(data: bytes) -> bytes:
    """转换为 PNG 格式（OpenAI 编辑接口要求）"""
    if not _HAS_PIL:
        return data
    try:
        img = Image.open(io.BytesIO(data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return data


# OpenAI API 基础地址（硬编码）
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")


def call_openai_generate(api_key: str, model: str, prompt: str, size: str = "") -> dict:
    """调用 OpenAI 文生图 API"""
    url = f"{OPENAI_BASE_URL}/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": _map_size(size),
    }

    result = http_post(url, headers=headers, json_data=payload)
    if "error" in result:
        return {"success": False, "error": result["error"]}
    if result.get("status", 0) not in (200,):
        return {"success": False, "error": f"HTTP {result.get('status')}: {result.get('text', '')[:200]}"}

    resp = result.get("json", {})
    urls = []
    for item in resp.get("data", []):
        if isinstance(item, dict):
            if item.get("url"):
                urls.append(item["url"])
            elif item.get("b64_json"):
                urls.append(f"data:image/png;base64,{item['b64_json']}")

    return {"success": True, "urls": urls}


def call_openai_edit(api_key: str, model: str, prompt: str, image_paths: list,
                     size: str = "") -> dict:
    """调用 OpenAI 图生图/编辑 API（multipart form）"""
    url = f"{OPENAI_BASE_URL}/images/edits"
    headers = {"Authorization": f"Bearer {api_key}"}

    target_size = _map_size(size)
    if not size and image_paths:
        # 根据第一张图自动选择尺寸
        try:
            data = read_image_file(image_paths[0])
            if _HAS_PIL:
                img = Image.open(io.BytesIO(data))
                target_size = _get_closest_size(*img.size)
        except Exception:
            pass

    files = []
    for i, path in enumerate(image_paths):
        data = _convert_to_png(read_image_file(path))
        # OpenAI edits 接口字段名固定为 "image"，支持多张
        files.append(("image", (f"image_{i}.png", data, "image/png")))

    # OpenAI edits 接口字段名固定为 "image"（单张）或支持多张
    # 这里用 requests/httpx 的 files 参数
    data_fields = {
        "prompt": prompt,
        "model": model,
        "n": "1",
        "size": target_size,
    }

    result = http_post(url, headers=headers, data=data_fields, files=files)
    if "error" in result:
        return {"success": False, "error": result["error"]}
    if result.get("status", 0) not in (200,):
        return {"success": False, "error": f"HTTP {result.get('status')}: {result.get('text', '')[:200]}"}

    resp = result.get("json", {})
    urls = []
    for item in resp.get("data", []):
        if isinstance(item, dict):
            if item.get("url"):
                urls.append(item["url"])
            elif item.get("b64_json"):
                urls.append(f"data:image/png;base64,{item['b64_json']}")

    return {"success": True, "urls": urls}


def main():
    args = parse_args()

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        output_error("未找到 OpenAI API 密钥，请设置 OPENAI_API_KEY 环境变量")
        return

    model = args.model
    if not model:
        output_error("--model 参数必填")
        return

    image_paths = []
    if args.images:
        for ident in args.images.split(","):
            ident = ident.strip()
            if not ident:
                continue
            path = resolve_image_file(ident)
            if path:
                image_paths.append(path)
            else:
                output_error(f"未找到图片标识符: {ident}")
                return

    if image_paths:
        result = call_openai_edit(api_key, model, args.prompt, image_paths, size=args.size)
    else:
        result = call_openai_generate(api_key, model, args.prompt, size=args.size)

    if not result.get("success"):
        output_error(result.get("error", "未知错误"))
        return

    urls = result.get("urls", [])
    if not urls:
        output_error("API 未返回图片数据")
        return

    # 处理结果（可能是 URL 或 base64 data URL）
    url = urls[0]
    if url.startswith("data:"):
        from _common import base64_to_image
        img_data = base64_to_image(url)
    else:
        # 下载 URL
        from _common import http_get
        resp = http_get(url)
        if "error" in resp or resp.get("status") != 200:
            output_error(f"下载图片失败: {resp.get('error') or resp.get('status')}")
            return
        img_data = resp.get("content") or resp.get("text", "").encode()

    stored = store_image(img_data, "ai")
    output_result(
        True,
        identifier=stored["identifier"],
        path=stored["path"],
        model=model,
    )


if __name__ == "__main__":
    main()
