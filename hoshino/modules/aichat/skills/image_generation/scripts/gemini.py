#!/usr/bin/env python3
"""
Gemini 图像生成/编辑脚本

支持：
- 文生图（generateContent）
- 图生图/编辑（generateContent + inlineData）
- aspect_ratio / size 参数

注意：prompt 已由 AI 按模型调优策略处理，脚本原样透传，不做任何修改。
"""
import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import (
    get_image_paths, resolve_image_file,
    store_image, read_image_file, http_post,
    output_result, output_error, parse_args
)


# Gemini API 基础地址（硬编码，如需自定义可通过环境变量覆盖）
GEMINI_BASE_URL = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")


def call_gemini_generate(api_key: str, model: str, prompt: str,
                         aspect_ratio: str = "", size: str = "") -> dict:
    """调用 Gemini 文生图 API"""
    base = GEMINI_BASE_URL.rstrip("/")
    url = f"{base}/models/{model}:generateContent"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    generation_config = {"responseModalities": ["IMAGE"]}
    if aspect_ratio or size:
        image_config = {}
        if aspect_ratio:
            image_config["aspectRatio"] = aspect_ratio
        if size:
            image_config["imageSize"] = size
        generation_config["imageGenerationConfig"] = image_config

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }

    result = http_post(url, headers=headers, json_data=payload)
    if "error" in result:
        return {"success": False, "error": result["error"]}
    if result.get("status", 0) not in (200,):
        return {"success": False, "error": f"HTTP {result.get('status')}: {result.get('text', '')[:200]}"}

    resp = result.get("json", {})
    urls = []
    for candidate in resp.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if "inlineData" in part:
                mime = part["inlineData"].get("mimeType", "image/png")
                data = part["inlineData"].get("data", "")
                if data:
                    urls.append(f"data:{mime};base64,{data}")

    return {"success": True, "urls": urls}


def call_gemini_edit(api_key: str, model: str, prompt: str, image_paths: list,
                     aspect_ratio: str = "", size: str = "") -> dict:
    """调用 Gemini 图生图/编辑 API"""
    base = GEMINI_BASE_URL.rstrip("/")
    url = f"{base}/models/{model}:generateContent"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    parts = []
    for path in image_paths:
        data = read_image_file(path)
        b64 = base64.b64encode(data).decode("utf-8")
        mime = "image/png"
        try:
            from PIL import Image
            img = Image.open(path)
            if img.format:
                mime = f"image/{img.format.lower()}"
        except Exception:
            pass
        parts.append({"inlineData": {"mimeType": mime, "data": b64}})

    parts.append({"text": prompt})

    generation_config = {"responseModalities": ["IMAGE"]}
    if aspect_ratio or size:
        image_config = {}
        if aspect_ratio:
            image_config["aspectRatio"] = aspect_ratio
        if size:
            image_config["imageSize"] = size
        generation_config["imageGenerationConfig"] = image_config

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": generation_config,
    }

    result = http_post(url, headers=headers, json_data=payload)
    if "error" in result:
        return {"success": False, "error": result["error"]}
    if result.get("status", 0) not in (200,):
        return {"success": False, "error": f"HTTP {result.get('status')}: {result.get('text', '')[:200]}"}

    resp = result.get("json", {})
    urls = []
    for candidate in resp.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if "inlineData" in part:
                mime = part["inlineData"].get("mimeType", "image/png")
                data = part["inlineData"].get("data", "")
                if data:
                    urls.append(f"data:{mime};base64,{data}")

    return {"success": True, "urls": urls}


def main():
    args = parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "")
    print(f"[gemini.py] GEMINI_API_KEY={api_key[:15]}..." if api_key else "[gemini.py] GEMINI_API_KEY=(未设置)", file=sys.stderr)
    if not api_key:
        output_error("未找到 Gemini API 密钥，请设置 GEMINI_API_KEY 环境变量")
        return

    model = args.model
    if not model:
        output_error("--model 参数必填")
        return

    # 解析待编辑图片
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
        result = call_gemini_edit(
            api_key, model, args.prompt, image_paths,
            aspect_ratio=args.aspect_ratio, size=args.size
        )
    else:
        result = call_gemini_generate(
            api_key, model, args.prompt,
            aspect_ratio=args.aspect_ratio, size=args.size
        )

    if not result.get("success"):
        output_error(result.get("error", "未知错误"))
        return

    urls = result.get("urls", [])
    if not urls:
        output_error("API 未返回图片数据")
        return

    # 存储第一张图片（目前各 API 通常只返回1张）
    from _common import base64_to_image
    img_data = base64_to_image(urls[0])
    stored = store_image(img_data, "ai")
    output_result(
        True,
        identifier=stored["identifier"],
        path=stored["path"],
        model=model,
    )


if __name__ == "__main__":
    main()
