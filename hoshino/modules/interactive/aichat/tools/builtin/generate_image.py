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

from hoshino.util import aiohttpx

from ..registry import tool_registry
from ...config import Config, ApiEntry

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
    description="根据文本描述生成图片。当用户要求画图、生成图片、或者需要视觉内容时使用此工具。",
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "图片的详细描述，用于生成图片。描述应该尽可能详细，包括场景、风格、颜色、物体等元素。"
            },
            "n": {
                "type": "integer",
                "description": "生成图片数量，范围 1-10。默认 1。",
                "minimum": 1,
                "maximum": 10
            }
        },
        "required": ["prompt"]
    }
)
async def generate_image(
    prompt: str,
    n: int = 1,
) -> Dict[str, Any]:
    """
    生成图片（使用配置的图像生成模型）
    
    Args:
        prompt: 图片描述
        n: 生成数量
    
    Returns:
        {"success": bool, "urls": List[str], "error": str}
    """
    try:
        target_model = conf.image_generation_model
        
        # 获取 API 配置
        api_config = _get_api_config_by_model(target_model)
        
        if not api_config:
            error_msg = f"未找到图片生成模型 {target_model} 的配置，且当前未配置 API"
            logger.error(error_msg)
            return {
                "success": False,
                "urls": [],
                "error": error_msg
            }
        
        api_key = api_config.api_key
        api_base = api_config.api_base.rstrip('/')
        model = api_config.model
        
        if not api_key:
            error_msg = f"图片生成模型 {model} 的 API Key 未配置"
            logger.error(error_msg)
            return {
                "success": False,
                "urls": [],
                "error": error_msg
            }
        
        # 构造请求
        url = f"{api_base}/images/generations"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "prompt": prompt,
            "n": min(max(n, 1), 10),  # 限制在 1-10 范围内
            "response_format": "b64_json"
        }
        
        logger.info(f"调用图片生成 API: {url}, model: {model}, prompt: {prompt[:50]}...")
        
        # 发送请求
        resp = await aiohttpx.post(url, headers=headers, json=payload)
        
        if not resp.ok:
            error_text = resp.text
            logger.error(f"图片生成 API 调用失败: {resp.status_code}, 响应: {error_text}")
            return {
                "success": False,
                "urls": [],
                "error": f"API 调用失败: HTTP {resp.status_code}, {error_text[:200]}"
            }
        
        result = resp.json
        if not result:
            logger.error("图片生成 API 返回空结果")
            return {
                "success": False,
                "urls": [],
                "error": "API 返回空结果"
            }
        
        # 提取图片 URL
        data = result.get("data", [])
        urls: List[str] = []
        
        for item in data:
            if isinstance(item, dict):
                # 优先使用 url 字段
                image_url = item.get("url")
                if image_url:
                    urls.append(image_url)
                    continue
                
                # 如果没有 url，尝试使用 b64_json
                b64_data = item.get("b64_json")
                if b64_data:
                    # 将 base64 数据转换为 data URL
                    data_url = f"data:image/png;base64,{b64_data}"
                    urls.append(data_url)
        
        if not urls:
            logger.error(f"无法从响应中提取图片 URL: {result}")
            return {
                "success": False,
                "urls": [],
                "error": "无法从 API 响应中提取图片 URL"
            }
        
        logger.info(f"成功生成 {len(urls)} 张图片")
        
        return {
            "success": True,
            "urls": urls,
            "error": None,
            "provider": model,
            "prompt": prompt,
            "n": len(urls)
        }
        
    except Exception as e:
        logger.exception(f"生成图片失败: {e}")
        return {
            "success": False,
            "urls": [],
            "error": str(e)
        }


@tool_registry.register(
    name="edit_image",
    description="""编辑用户上传的图片，根据描述修改图片内容或风格。

当用户要求修改图片时使用此工具。

图片选择方式：
- 使用 image_index 指定要编辑的图片：-1 表示最近上传的图片（默认），-2 表示倒数第二张，以此类推
- 如果提供了 image_url，则直接使用该 URL 编辑（优先级高于 image_index）

编辑描述应尽可能详细，说明要修改的具体内容。""",
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "编辑描述，说明如何修改图片。例如：\"把猫改成黑色的\"、\"添加一个太阳\"等"
            },
            "image_index": {
                "type": "integer",
                "description": "图片索引，-1表示最近上传的图片，-2表示倒数第二张，默认-1",
                "default": -1
            },
            "image_url": {
                "type": "string",
                "description": "可选：直接提供图片的 URL 或 base64 data URL，如果提供则优先使用",
                "default": ""
            }
        },
        "required": ["prompt"]
    },
    inject_session=True  # 启用 session 自动注入
)
async def edit_image(
    prompt: str,
    image_index: int = -1,
    image_url: str = "",
    session: Optional["Session"] = None,  # 由装饰器自动注入
) -> Dict[str, Any]:
    """
    编辑已有图片（使用配置的图片编辑模型，如 DALL-E 2）
    
    Args:
        image_url: 原图片 URL 或 base64 data URL
        prompt: 编辑描述
    
    Returns:
        {"success": bool, "urls": List[str], "error": str}
    """
    try:
        target_model = conf.image_edit_model
        
        # 检查是否配置了编辑模型
        if not target_model:
            return {
                "success": False,
                "urls": [],
                "error": "图片编辑功能未配置，请在 aichat 配置中设置 image_edit_model（如 dall-e-2）"
            }
        
        # 获取 API 配置
        api_config = _get_api_config_by_model(target_model)
        
        if not api_config:
            error_msg = f"未找到图片编辑模型 {target_model} 的配置，且当前未配置 API"
            logger.error(error_msg)
            return {
                "success": False,
                "urls": [],
                "error": error_msg
            }
        
        api_key = api_config.api_key
        api_base = api_config.api_base.rstrip('/')
        model = api_config.model
        
        if not api_key:
            error_msg = f"图片编辑模型 {model} 的 API Key 未配置"
            logger.error(error_msg)
            return {
                "success": False,
                "urls": [],
                "error": error_msg
            }
        
        # 获取原图
        if not image_url:
            # 未提供 URL，尝试通过 image_index 从 session 获取
            if session is None:
                return {
                    "success": False,
                    "urls": [],
                    "error": "无法获取会话信息，请重试或提供图片 URL"
                }
            
            image_url = session.get_image_by_index(image_index)
            
            if not image_url:
                return {
                    "success": False,
                    "urls": [],
                    "error": f"未找到索引为 {image_index} 的图片，请确认已上传图片或使用其他索引"
                }
        
        # 检查是否是工具图片占位符（如 <<tool_img_1>>）
        if image_url.startswith("<<tool_img_") and session:
            base64_data = session.get_tool_image(image_url)
            if base64_data:
                image_url = base64_data
            else:
                return {
                    "success": False,
                    "urls": [],
                    "error": f"未找到占位符对应的图片: {image_url}"
                }
        
        image_bytes = await _get_image_bytes(image_url)
        if not image_bytes:
            return {
                "success": False,
                "urls": [],
                "error": "无法获取原图，请检查图片 URL 或 base64 数据是否有效"
            }
        
        # 转换为 PNG 格式（DALL-E 要求）
        image_bytes = _convert_to_png(image_bytes)
        
        # 构造 multipart 请求
        url = f"{api_base}/images/edits"
        
        async with ClientSession() as session:
            form = FormData()
            form.add_field('image', image_bytes, filename='image.png', content_type='image/png')
            form.add_field('prompt', prompt)
            
            # 可选参数
            form.add_field('n', '1')
            form.add_field('size', '1024x1024')
            
            headers = {
                "Authorization": f"Bearer {api_key}"
            }
            
            logger.info(f"调用图片编辑 API: {url}, model: {model}, prompt: {prompt[:50]}...")
            
            async with session.post(url, headers=headers, data=form) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"图片编辑 API 调用失败: {resp.status}, 响应: {error_text}")
                    return {
                        "success": False,
                        "urls": [],
                        "error": f"API 调用失败: HTTP {resp.status}, {error_text[:200]}"
                    }
                
                result = await resp.json()
        
        if not result:
            logger.error("图片编辑 API 返回空结果")
            return {
                "success": False,
                "urls": [],
                "error": "API 返回空结果"
            }
        
        # 提取图片 URL
        data = result.get("data", [])
        urls: List[str] = []
        
        for item in data:
            if isinstance(item, dict):
                image_url = item.get("url")
                if image_url:
                    urls.append(image_url)
                    continue
                
                b64_data = item.get("b64_json")
                if b64_data:
                    data_url = f"data:image/png;base64,{b64_data}"
                    urls.append(data_url)
        
        if not urls:
            logger.error(f"无法从响应中提取图片 URL: {result}")
            return {
                "success": False,
                "urls": [],
                "error": "无法从 API 响应中提取图片 URL"
            }
        
        logger.info(f"成功编辑图片，生成 {len(urls)} 张")
        
        return {
            "success": True,
            "urls": urls,
            "error": None,
            "provider": model,
            "prompt": prompt,
            "n": len(urls)
        }
        
    except Exception as e:
        logger.exception(f"编辑图片失败: {e}")
        return {
            "success": False,
            "urls": [],
            "error": str(e)
        }
