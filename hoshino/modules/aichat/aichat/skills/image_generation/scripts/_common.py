"""
image_generation Skill 共享工具模块

不依赖 hoshino/NoneBot，供各服务商脚本共用。
"""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------- image_store_core 动态加载 ----------
_project_root = Path(os.environ.get("PROJECT_ROOT", "."))
_core_path = _project_root / "hoshino" / "modules" / "aichat" / "_image_store_core.py"

if _core_path.exists():
    import importlib.util
    spec = importlib.util.spec_from_file_location("image_store_core", str(_core_path))
    image_store_core = importlib.util.module_from_spec(spec)
    sys.modules["image_store_core"] = image_store_core
    spec.loader.exec_module(image_store_core)
    ImageStoreCore = image_store_core.ImageStoreCore
    ImageEntry = image_store_core.ImageEntry
else:
    raise RuntimeError(f"_image_store_core.py not found at {_core_path}")


# ---------- 图片路径解析 ----------

def get_image_paths() -> Dict[str, str]:
    """从 SKILL_IMAGES 环境变量获取标识符→路径映射"""
    raw = os.environ.get("SKILL_IMAGES", "{}")
    try:
        return json.loads(raw)
    except Exception:
        return {}


def resolve_image_file(identifier: str) -> Optional[str]:
    """将标识符解析为本地文件路径"""
    identifier = identifier.strip()
    if not identifier.startswith("<"):
        identifier = f"<{identifier}>"
    paths = get_image_paths()
    return paths.get(identifier)


# ---------- 图片存储 ----------

def store_image(data: bytes, source: str, ext: str = "png") -> Dict[str, Any]:
    """存储图片到 Session ImageStore

    Returns:
        {"identifier": "...", "path": "..."}
    """
    session_id = os.environ.get("SESSION_ID", "unknown")
    store = ImageStoreCore(session_id)
    entry = store.store_bytes(data, source, ext)
    return {
        "identifier": entry.identifier,
        "path": str(entry.file_path),
        "format": entry.format,
        "width": entry.width,
        "height": entry.height,
    }


def read_image_file(path: str) -> bytes:
    """读取本地图片文件为 bytes"""
    with open(path, "rb") as f:
        return f.read()


def image_to_base64(data: bytes, mime: str = "image/png") -> str:
    """bytes → base64 data URL"""
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def base64_to_image(data_url: str) -> bytes:
    """base64 data URL → bytes"""
    if "," in data_url:
        b64 = data_url.split(",", 1)[1]
    else:
        b64 = data_url
    return base64.b64decode(b64)


# ---------- HTTP 工具 ----------

import httpx


def _parse_response(resp: httpx.Response) -> Dict[str, Any]:
    """解析 httpx 响应。JSON/文本放 text/json，二进制放 content。"""
    content_type = resp.headers.get("Content-Type", "")
    if "application/json" in content_type or content_type.startswith("text/"):
        try:
            j = resp.json()
        except Exception:
            j = None
        return {"status": resp.status_code, "text": resp.text, "json": j}
    else:
        return {"status": resp.status_code, "content": resp.content}


def http_post(url: str,
              headers: Optional[Dict[str, str]] = None,
              json_data: Optional[Dict[str, Any]] = None,
              data: Optional[Any] = None,
              files: Optional[Any] = None,
              timeout: int = 180) -> Dict[str, Any]:
    """同步 POST 请求"""
    try:
        with httpx.Client(timeout=timeout) as client:
            if files:
                resp = client.post(url, headers=headers, data=data, files=files)
            elif json_data is not None:
                resp = client.post(url, headers=headers, json=json_data)
            else:
                resp = client.post(url, headers=headers, data=data)
            return _parse_response(resp)
    except Exception as e:
        return {"error": str(e)}


def http_get(url: str,
             headers: Optional[Dict[str, str]] = None,
             timeout: int = 180) -> Dict[str, Any]:
    """同步 GET 请求"""
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=headers)
            return _parse_response(resp)
    except Exception as e:
        return {"error": str(e)}


# ---------- 通用输出 ----------

def output_result(success: bool, identifier: str = "", path: str = "",
                  model: str = "", error: str = "") -> None:
    """输出标准 JSON 结果到 stdout"""
    result: Dict[str, Any] = {"success": success}
    if identifier:
        result["identifier"] = identifier
    if path:
        result["path"] = path
    if model:
        result["model"] = model
    if error:
        result["error"] = error
    print(json.dumps(result, ensure_ascii=False))


def output_error(error: str) -> None:
    """输出错误结果"""
    output_result(False, error=error)


# ---------- 参数解析 ----------

def parse_args() -> argparse.Namespace:
    """统一参数解析"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True, help="图像描述/编辑指令（已调优）")
    parser.add_argument("--images", default="", help="待编辑图片标识符，逗号分隔")
    parser.add_argument("--aspect-ratio", default="", help="宽高比")
    parser.add_argument("--size", default="", help="分辨率")
    parser.add_argument("--model", default="", help="模型名称（由 AI 选择）")
    return parser.parse_args()
