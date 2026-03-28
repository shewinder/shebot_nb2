"""
AI 工具：图片生成与编辑
根据文本描述生成图片或编辑已有图片
"""
import base64
import io
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ...session import Session
from loguru import logger

from aiohttp import ClientSession
from aiohttp import FormData
from PIL import Image

from hoshino.util import aiohttpx, truncate_log, log_json

from ..registry import tool_registry, ok, fail
from ...config import Config, ApiEntry, ImageModelEntry

# 加载配置
conf = Config.get_instance('aichat')


def _get_api_config_by_model(model_name: str) -> Optional[ApiEntry]:
    """
    根据模型名称查找 API 配置
    
    1. 首先精确匹配 model 字段
    2. 如果没找到，使用当前选中的 API 的 base/key，但 model 保持为传入值
    
    Args:
        model_name: 模型名称
    
    Returns:
        ApiEntry 或 None
    """
    if not model_name:
        return None
    
    # 1. 精确匹配 model 字段
    for api in conf.get_apis():
        if api.model == model_name:
            return api
    
    # 2. 没找到，使用当前 API 的 base/key，但替换 model
    current_api_name = conf.get_current_api()
    current_api = conf.get_api_by_name(current_api_name)
    if current_api:
        logger.info(f"未找到模型 {model_name} 的配置，使用当前 API ({current_api.api}) 的 base/key，但模型保持为 {model_name}")
        # 创建新的配置，保持 model 为传入的模型名
        return ApiEntry(
            api=current_api.api,
            api_key=current_api.api_key,
            api_base=current_api.api_base,
            model=model_name,  # 使用传入的模型名，而非当前 API 的 model
        )
    
    return None


async def _download_image(image_url: str) -> Optional[bytes]:
    """下载图片并返回字节数据"""
    try:
        resp = await aiohttpx.get(image_url)
        if not resp.ok:
            logger.error(f"下载图片失败: {resp.status_code}, URL: {image_url}")
            return None
        return resp.content
    except Exception as e:
        logger.exception(f"下载图片失败: {e}, URL: {image_url}")
        return None


def _select_image_model(image_count: int) -> Optional[ImageModelEntry]:
    """根据图片数量选择第一个匹配的模型"""
    required = "multi_edit" if image_count > 1 else ("edit" if image_count == 1 else "generate")
    
    for model in conf.image_models:
        if required in model.capabilities:
            return model
    
    # 降级：multi_edit -> edit
    if required == "multi_edit":
        for model in conf.image_models:
            if "edit" in model.capabilities:
                logger.warning("未找到支持 multi_edit 的模型，降级使用单图 edit")
                return model
    
    return None





async def _get_image_bytes(image_url_or_data: str) -> Optional[bytes]:
    """
    获取图片字节数据
    
    支持两种格式：
    1. 普通 URL: https://example.com/image.png
    2. Data URL: data:image/png;base64,iVBORw0KGgo...
    
    Args:
        image_url_or_data: 图片 URL 或 base64 data URL
    
    Returns:
        图片字节数据，失败返回 None
    """
    if not image_url_or_data:
        return None
    
    # 检查是否是 data URL
    if image_url_or_data.startswith('data:image'):
        try:
            # data:image/png;base64,xxxxx
            # data:image/jpeg;base64,xxxxx
            if ',' in image_url_or_data:
                base64_part = image_url_or_data.split(',')[1]
                return base64.b64decode(base64_part)
            else:
                logger.error(f"无效的 data URL 格式: {image_url_or_data[:50]}...")
                return None
        except Exception as e:
            logger.exception(f"解析 base64 data URL 失败: {e}")
            return None
    else:
        # 普通 URL，下载图片
        return await _download_image(image_url_or_data)


def _convert_to_png(image_bytes: bytes) -> bytes:
    """将图片转换为 PNG 格式"""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        # 转换为 RGB 模式（去除透明通道，兼容性好）
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        output = io.BytesIO()
        img.save(output, format='PNG')
        return output.getvalue()
    except Exception as e:
        logger.exception(f"图片格式转换失败: {e}")
        # 转换失败返回原数据
        return image_bytes


@tool_registry.register(
    name="generate_image",
    description="""生成或编辑图片。

根据传入的参数自动选择合适的能力：
- 仅提供 prompt：根据描述生成新图片
- 提供单张图片：编辑该图片（如改变风格、添加元素）
- 提供多张图片：融合图片（如让人物穿衣服、替换背景）

注意：部分模型不支持编辑或多图融合，将自动选择合适的模型或提示错误。""",
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "图片描述或编辑指令。生成时描述要画的内容；编辑时描述如何修改（如\"把猫变成黑色\"、\"让这个人穿上这件衣服\"）"
            },
            "image_identifiers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "图片标识符列表（可选），用于编辑或融合图片。从对话中的[当前可用图片]列表获取，如 <user_image_1>, <ai_image_1>"
            }
        },
        "required": ["prompt"]
    },
)
async def generate_image(
    prompt: str,
    session: "Session",
    image_identifiers: List[str] = None,
) -> Dict[str, Any]:
    """
    生成或编辑图片
    
    Args:
        prompt: 图片描述或编辑指令
        session: 会话对象（自动注入）
        image_identifiers: 图片标识符列表（可选）
    
    Returns:
        {"success": bool, "content": str, "images": List[str], "error": str, "metadata": Dict}
    """
    try:
        image_identifiers = image_identifiers or []
        image_count = len(image_identifiers)
        
        # 选择模型配置
        model_entry = _select_image_model(image_count)
        if not model_entry:
            error_msg = "未找到可用的图片生成模型"
            logger.error(error_msg)
            return fail(error_msg)
        
        target_model = model_entry.model
        api_format = model_entry.api_format
        
        # 获取 API 配置
        api_config = _get_api_config_by_model(target_model)
        
        if not api_config:
            error_msg = f"未找到模型 {target_model} 的 API 配置"
            logger.error(error_msg)
            return fail(error_msg)
        
        api_key = api_config.api_key
        api_base = api_config.api_base.rstrip('/')
        
        if not api_key:
            error_msg = f"模型 {target_model} 的 API Key 未配置"
            logger.error(error_msg)
            return fail(error_msg)
        
        # 根据图片数量和 API 格式调用不同接口
        if image_count == 0:
            # 纯生成
            result = await _call_generate_api(api_base, api_key, target_model, api_format, prompt)
        else:
            # 编辑/融合
            image_urls = []
            for identifier in image_identifiers:
                image_data = session.resolve_image_identifier(identifier)
                if not image_data:
                    error_msg = f"未找到图片标识符: {identifier}"
                    logger.error(error_msg)
                    return fail(error_msg)
                # 获取图片 URL（如果是 base64，需要上传或处理）
                image_urls.append(image_data)
            
            # OpenAI 格式只支持单图编辑
            if api_format != "gemini" and image_count > 1:
                logger.warning(f"OpenAI 格式不支持多图融合，只使用第一张图")
                image_urls = [image_urls[0]]
            
            result = await _call_edit_api(api_base, api_key, target_model, api_format, prompt, image_urls)
        
        if not result.get("success"):
            return fail(result.get("error", "API 调用失败"))
        
        urls = result.get("urls", [])
        if not urls:
            error_msg = "无法从 API 响应中获取图片"
            logger.error(error_msg)
            return fail(error_msg)
        
        logger.info(f"成功生成/编辑 {len(urls)} 张图片")
        
        # 存储图片到 session
        identifiers = []
        for url in urls:
            identifier = session.store_ai_image(url)
            identifiers.append(identifier)
            logger.info(f"generate_image: 存储 AI 图片 {identifier}")
        
        # 构造 content：描述性文字，不包含标识符（避免 AI 在回复中输出标识符）
        # 标识符通过 metadata 传给 AI，让 AI 知道可以用什么引用
        if identifiers:
            if len(identifiers) == 1:
                content = "已成功生成图片。"
            else:
                content = f"已成功生成 {len(identifiers)} 张图片。"
        else:
            content = f"已成功生成 {len(urls)} 张图片"
        
        return ok(
            content,
            images=urls,
            metadata={
                "identifiers": identifiers,
                "model": target_model,
                "prompt": prompt,
                "n": len(urls)
            }
        )
        
    except Exception as e:
        logger.exception(f"生成图片失败: {e}")
        return fail(f"图片生成失败: {str(e)}", error=str(e))


async def _call_generate_api(
    api_base: str,
    api_key: str,
    model: str,
    api_format: str,
    prompt: str
) -> Dict[str, Any]:
    """调用图片生成 API"""
    if api_format == "gemini":
        # Gemini 官方格式: generateContent
        # 处理 api_base 可能包含版本号的情况
        base = api_base.rstrip('/')
        if '/v1' in base and not base.endswith('/v1beta'):
            # 如果 base 包含 /v1 但不以 /v1beta 结尾，替换或追加
            base = base.replace('/v1', '/v1beta')
        url = f"{base}/models/{model}:generateContent"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "responseModalities": ["IMAGE"]
            }
        }
    else:
        url = f"{api_base}/images/generations"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json"
        }
    
    logger.info(f"调用生成 API: {url}, model: {model}, prompt: {truncate_log(prompt)}")
    resp = await aiohttpx.post(url, headers=headers, json=payload)
    
    if not resp.ok:
        error_text = truncate_log(resp.text) if hasattr(resp, 'text') else str(resp)
        logger.error(f"API 调用失败: {resp.status_code if hasattr(resp, 'status_code') else 'unknown'}, {error_text}")
        return {"success": False, "error": f"HTTP {getattr(resp, 'status_code', 'unknown')}: {str(error_text)[:200]}"}
    
    result = resp.json if hasattr(resp, 'json') else resp.json()
    logger.info(f"生成 API 响应: {log_json(result)}")
    if not result:
        return {"success": False, "error": "API 返回空结果"}
    
    urls = []
    if api_format == "gemini":
        # Gemini 响应: candidates[0].content.parts[].inlineData.data (base64)
        candidates = result.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "inlineData" in part:
                    mime_type = part["inlineData"].get("mimeType", "image/png")
                    data = part["inlineData"].get("data", "")
                    if data:
                        urls.append(f"data:{mime_type};base64,{data}")
    else:
        for item in result.get("data", []):
            if isinstance(item, dict):
                if item.get("url"):
                    urls.append(item["url"])
                elif item.get("b64_json"):
                    urls.append(f"data:image/png;base64,{item['b64_json']}")
    
    return {"success": True, "urls": urls}


async def _call_edit_api(
    api_base: str,
    api_key: str,
    model: str,
    api_format: str,
    prompt: str,
    image_urls: List[str]
) -> Dict[str, Any]:
    """调用图片编辑 API"""
    if api_format == "gemini":
        # Gemini 官方格式: 多图作为 inlineData
        base = api_base.rstrip('/')
        if '/v1' in base and not base.endswith('/v1beta'):
            base = base.replace('/v1', '/v1beta')
        url = f"{base}/models/{model}:generateContent"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # 构建 parts: 先添加所有图片，再添加文本 prompt
        parts = []
        for image_url in image_urls:
            image_bytes = await _get_image_bytes(image_url)
            if image_bytes:
                # 检测 MIME 类型
                mime_type = "image/png"
                try:
                    with Image.open(io.BytesIO(image_bytes)) as img:
                        if img.format:
                            mime_type = f"image/{img.format.lower()}"
                except:
                    pass
                # 转换为 base64
                b64_data = base64.b64encode(image_bytes).decode('utf-8')
                parts.append({
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": b64_data
                    }
                })
        
        parts.append({"text": prompt})
        
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseModalities": ["IMAGE"]
            }
        }
        
        logger.info(f"调用 Gemini 编辑 API: {url}, 图片数: {len(image_urls)}, prompt: {truncate_log(prompt)}")
        resp = await aiohttpx.post(url, headers=headers, json=payload)
        
        if not resp.ok:
            error_text = truncate_log(resp.text) if hasattr(resp, 'text') else str(resp)
            logger.error(f"API 调用失败: {getattr(resp, 'status_code', 'unknown')}, {error_text}")
            return {"success": False, "error": f"HTTP {getattr(resp, 'status_code', 'unknown')}: {str(error_text)[:200]}"}
        
        result = resp.json if hasattr(resp, 'json') else resp.json()
        logger.info(f"Gemini 编辑 API 响应: {log_json(result)}")
        urls = []
        candidates = result.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "inlineData" in part:
                    mime_type = part["inlineData"].get("mimeType", "image/png")
                    data = part["inlineData"].get("data", "")
                    if data:
                        urls.append(f"data:{mime_type};base64,{data}")
        
        return {"success": True, "urls": urls}
    else:
        # OpenAI 格式只支持单图
        image_url = image_urls[0]
        image_bytes = await _get_image_bytes(image_url)
        if not image_bytes:
            return {"success": False, "error": "无法获取图片数据"}
        
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                width, height = img.size
                target_size = _get_closest_size(width, height)
        except:
            target_size = "1024x1024"
        
        image_bytes = _convert_to_png(image_bytes)
        
        url = f"{api_base}/images/edits"
        
        async with ClientSession() as http_session:
            form = FormData()
            form.add_field('image', image_bytes, filename='image.png', content_type='image/png')
            form.add_field('prompt', prompt)
            form.add_field('n', '1')
            form.add_field('size', target_size)
            
            headers = {"Authorization": f"Bearer {api_key}"}
            logger.info(f"调用 OpenAI 编辑 API: {url}")
            async with http_session.post(url, headers=headers, data=form) as resp:
                if resp.status != 200:
                    error_text = truncate_log(await resp.text())
                    logger.error(f"API 调用失败: {resp.status}, {error_text}")
                    return {"success": False, "error": f"HTTP {resp.status}: {error_text[:200]}"}
                result = await resp.json()
                logger.info(f"OpenAI 编辑 API 响应: {log_json(result)}")
                
                urls = []
                for item in result.get("data", []):
                    if isinstance(item, dict):
                        if item.get("url"):
                            urls.append(item["url"])
                        elif item.get("b64_json"):
                            urls.append(f"data:image/png;base64,{item['b64_json']}")
                
                return {"success": True, "urls": urls}


def _get_closest_size(width: int, height: int) -> str:
    """
    根据原图分辨率获取最接近的标准尺寸
    
    gpt-image-1 支持的标准尺寸:
    - 1024x1024 (正方形)
    - 1536x1024 (横屏)
    - 1024x1536 (竖屏)
    - auto (自动选择)
    
    根据宽高比选择最接近的标准尺寸
    """
    # 计算宽高比
    aspect_ratio = width / height
    
    # 标准尺寸的宽高比
    # 正方形: 1.0, 横屏: 1.5, 竖屏: 0.67
    if aspect_ratio >= 1.3:
        # 横屏图片，使用 1536x1024
        return "1536x1024"
    elif aspect_ratio <= 0.7:
        # 竖屏图片，使用 1024x1536
        return "1024x1536"
    else:
        # 接近正方形，使用 1024x1024
        return "1024x1024"

