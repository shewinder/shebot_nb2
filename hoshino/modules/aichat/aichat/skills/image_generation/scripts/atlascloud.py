#!/usr/bin/env python3
"""
AtlasCloud 图像生成/编辑脚本

支持：
- 文生图（generateImage + 轮询 prediction）
- 图生图（编辑，需先 uploadMedia 上传图片）
- 多图融合（images 字段）

注意：prompt 已由 AI 按模型调优策略处理，脚本原样透传，不做任何修改。
"""
import base64
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import (
    get_image_paths, resolve_image_file,
    store_image, read_image_file, http_post, http_get,
    output_result, output_error, parse_args
)


# AtlasCloud API 基础地址（硬编码）
ATLAS_BASE_URL = "https://api.atlascloud.ai/api/v1"


def _upload_media(api_key: str, image_bytes: bytes) -> str:
    """上传图片到 AtlasCloud 获取临时 URL"""
    url = f"{ATLAS_BASE_URL}/model/uploadMedia"
    headers = {"Authorization": f"Bearer {api_key}"}

    import io
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
    except Exception:
        png_bytes = image_bytes

    result = http_post(url, headers=headers, files={"file": ("image.png", png_bytes, "image/png")})
    if "error" in result:
        raise RuntimeError(f"上传失败: {result['error']}")
    if result.get("status", 0) not in (200,):
        raise RuntimeError(f"上传失败 HTTP {result.get('status')}: {result.get('text', '')[:200]}")

    resp = result.get("json", {})
    temp_url = resp.get("url") or resp.get("data", {}).get("download_url")
    if not temp_url:
        raise RuntimeError(f"上传未返回临时 URL: {resp}")
    return temp_url


def _poll_prediction(api_key: str, prediction_id: str) -> list:
    """轮询 AtlasCloud 预测任务，返回图片 URL 列表"""
    poll_url = f"{ATLAS_BASE_URL}/model/prediction/{prediction_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = 300
    interval = 2
    elapsed = 0

    while elapsed < timeout:
        result = http_get(poll_url, headers=headers)
        if "error" in result:
            raise RuntimeError(f"轮询失败: {result['error']}")

        resp = result.get("json", {})
        status = resp.get("data", {}).get("status")
        if status == "completed":
            outputs = resp.get("data", {}).get("outputs", [])
            return outputs
        elif status == "failed":
            error_msg = resp.get("data", {}).get("error", "未知错误")
            raise RuntimeError(f"AtlasCloud 生成失败: {error_msg}")

        time.sleep(interval)
        elapsed += interval

    raise RuntimeError("AtlasCloud 生成超时")


def call_atlascloud_generate(api_key: str, model: str, prompt: str) -> dict:
    """调用 AtlasCloud 文生图 API"""
    url = f"{ATLAS_BASE_URL}/model/generateImage"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "prompt": prompt,
    }

    result = http_post(url, headers=headers, json_data=payload)
    if "error" in result:
        return {"success": False, "error": result["error"]}
    if result.get("status", 0) not in (200,):
        return {"success": False, "error": f"HTTP {result.get('status')}: {result.get('text', '')[:200]}"}

    resp = result.get("json", {})
    prediction_id = resp.get("data", {}).get("id")
    if not prediction_id:
        return {"success": False, "error": "AtlasCloud 未返回 prediction id"}

    try:
        urls = _poll_prediction(api_key, prediction_id)
        return {"success": True, "urls": urls}
    except Exception as e:
        return {"success": False, "error": str(e)}


def call_atlascloud_edit(api_key: str, model: str, prompt: str, image_paths: list) -> dict:
    """调用 AtlasCloud 图生图/编辑 API"""
    # 上传所有图片获取临时 URL
    temp_urls = []
    for path in image_paths:
        data = read_image_file(path)
        try:
            temp_url = _upload_media(api_key, data)
            temp_urls.append(temp_url)
        except Exception as e:
            return {"success": False, "error": f"上传图片失败: {e}"}

    url = f"{ATLAS_BASE_URL}/model/generateImage"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if len(temp_urls) == 1:
        payload = {
            "model": model,
            "prompt": prompt,
            "image": temp_urls[0],
        }
    else:
        payload = {
            "model": model,
            "prompt": prompt,
            "images": temp_urls,
        }

    result = http_post(url, headers=headers, json_data=payload)
    if "error" in result:
        return {"success": False, "error": result["error"]}
    if result.get("status", 0) not in (200,):
        return {"success": False, "error": f"HTTP {result.get('status')}: {result.get('text', '')[:200]}"}

    resp = result.get("json", {})
    prediction_id = resp.get("data", {}).get("id")
    if not prediction_id:
        return {"success": False, "error": "AtlasCloud 未返回 prediction id"}

    try:
        urls = _poll_prediction(api_key, prediction_id)
        return {"success": True, "urls": urls}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    args = parse_args()

    api_key = os.environ.get("ATLAS_API_KEY", "")
    print(f"[atlascloud.py] ATLAS_API_KEY={api_key[:15]}..." if api_key else "[atlascloud.py] ATLAS_API_KEY=(未设置)", file=sys.stderr)
    if not api_key:
        output_error("未找到 AtlasCloud API 密钥，请设置 ATLAS_API_KEY 环境变量")
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
        result = call_atlascloud_edit(api_key, model, args.prompt, image_paths)
    else:
        result = call_atlascloud_generate(api_key, model, args.prompt)

    if not result.get("success"):
        output_error(result.get("error", "未知错误"))
        return

    urls = result.get("urls", [])
    if not urls:
        output_error("API 未返回图片数据")
        return

    # 下载图片并存储
    url = urls[0]
    if url.startswith("data:"):
        from _common import base64_to_image
        img_data = base64_to_image(url)
    else:
        resp = http_get(url)
        if "error" in resp or resp.get("status") not in (200,):
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
