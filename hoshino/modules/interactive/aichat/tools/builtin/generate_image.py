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
    },
    inject_session=True  # 启用 session 自动注入
)
async def generate_image(
    prompt: str,
    n: int = 1,
    session: Optional["Session"] = None,  # 由装饰器自动注入
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
                "content": error_msg,
                "images": [],
                "error": error_msg,
                "metadata": {}
            }
        
        api_key = api_config.api_key
        api_base = api_config.api_base.rstrip('/')
        model = api_config.model
        
        if not api_key:
            error_msg = f"图片生成模型 {model} 的 API Key 未配置"
            logger.error(error_msg)
            return {
                "success": False,
                "content": error_msg,
                "images": [],
                "error": error_msg,
                "metadata": {}
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
                "content": "无法从 API 响应中提取图片 URL",
                "images": [],
                "error": "无法从 API 响应中提取图片 URL",
                "metadata": {}
            }
        
        logger.info(f"成功生成 {len(urls)} 张图片")
        
        # ===== 标准化返回格式 =====
        # 将图片存入 AI 图片列表，获取统一标识符
        identifiers = []
        if session and urls:
            for url in urls:
                identifier = session.store_ai_image(url)
                identifiers.append(identifier)
                logger.info(f"generate_image: 存储 AI 图片 {identifier}")
        
        # 构造 content：告诉 AI 标识符
        if identifiers:
            if len(identifiers) == 1:
                content = f"已成功生成图片 {identifiers[0]}。"
            else:
                id_str = ", ".join(identifiers)
                content = f"已成功生成 {len(identifiers)} 张图片：{id_str}。"
        else:
            content = f"已成功生成 {len(urls)} 张图片"
        
        return {
            "success": True,
            "content": content,
            "images": urls,  # 真实图片，用于发送
            "error": None,
            "metadata": {
                "identifiers": identifiers,  # AI 实际看到的标识符
                "model": model,
                "prompt": prompt,
                "n": len(urls)
            }
        }
        
    except Exception as e:
        logger.exception(f"生成图片失败: {e}")
        return {
            "success": False,
            "content": f"图片生成失败: {str(e)}",
            "images": [],
            "error": str(e),
            "metadata": {}
        }


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


@tool_registry.register(
    name="edit_image",
    description="""编辑已有图片。

使用图片标识符指定要编辑的图片（从[当前可用图片]列表中选择）：
- <我发的图片-1>, <我发的图片-2> ...（用户发送的图片）
- <你发的图片-1>, <你发的图片-2> ...（你之前生成的图片）
- <链接图片-1>, <链接图片-2> ...（引用消息中的图片）

使用方法：将标识符（如 <你发的图片-1>）作为 image_identifier 参数传入。
注意：标识符仅用于工具参数，不要输出在回复中给用户看。""",
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "编辑描述，说明如何修改图片。例如：\"把猫改成黑色的\"、\"添加一个太阳\"等"
            },
            "image_identifier": {
                "type": "string",
                "description": "要编辑的图片标识符，如 <我发的图片-1>, <你发的图片-1> 等，从对话中的[当前可用图片]列表获取。如果不提供，将自动使用最近的一张图片。"
            }
        },
        "required": ["prompt"]
    },
    inject_session=True  # 启用 session 自动注入
)
async def edit_image(
    prompt: str,
    image_identifier: str = "",
    session: Optional["Session"] = None,  # 由装饰器自动注入
) -> Dict[str, Any]:
    """
    编辑已有图片（使用配置的图片编辑模型，如 DALL-E 2）
    
    Args:
        prompt: 编辑描述
        image_identifier: 图片标识符（如 <我发的图片-1>, <你发的图片-1>）
    
    Returns:
        {"success": bool, "content": str, "images": List[str], "error": str, "metadata": Dict}
    """
    try:
        target_model = conf.image_edit_model
        
        # 检查是否配置了编辑模型
        if not target_model:
            return {
                "success": False,
                "content": "图片编辑功能未配置，请在 aichat 配置中设置 image_edit_model（如 dall-e-2）",
                "images": [],
                "error": "图片编辑功能未配置，请在 aichat 配置中设置 image_edit_model（如 dall-e-2）",
                "metadata": {}
            }
        
        # 获取 API 配置
        api_config = _get_api_config_by_model(target_model)
        
        if not api_config:
            error_msg = f"未找到图片编辑模型 {target_model} 的配置，且当前未配置 API"
            logger.error(error_msg)
            return {
                "success": False,
                "content": error_msg,
                "images": [],
                "error": error_msg,
                "metadata": {}
            }
        
        api_key = api_config.api_key
        api_base = api_config.api_base.rstrip('/')
        model = api_config.model
        
        if not api_key:
            error_msg = f"图片编辑模型 {model} 的 API Key 未配置"
            logger.error(error_msg)
            return {
                "success": False,
                "content": error_msg,
                "images": [],
                "error": error_msg,
                "metadata": {}
            }
        
        # 获取原图
        image_data = None
        
        if not image_identifier:
            # 未提供标识符，使用最近的一张图片
            if session is None:
                logger.error("edit_image: session 为 None，无法获取图片")
                return {
                    "success": False,
                    "content": "无法获取会话信息，请重试或提供图片标识符",
                    "images": [],
                    "error": "无法获取会话信息，请重试或提供图片标识符",
                    "metadata": {}
                }
            
            last_image = session.get_last_image()
            if last_image:
                identifier, image_data = last_image
                logger.info(f"edit_image: 使用最近的图片 {identifier}")
            else:
                logger.warning("edit_image: 未找到任何可用图片")
                return {
                    "success": False,
                    "content": "未找到任何可用图片，请先上传图片或生成图片",
                    "images": [],
                    "error": "未找到任何可用图片",
                    "metadata": {}
                }
        else:
            # 解析标识符获取图片
            if session is None:
                logger.error("edit_image: session 为 None，无法解析标识符")
                return {
                    "success": False,
                    "content": "无法获取会话信息，请重试",
                    "images": [],
                    "error": "无法获取会话信息",
                    "metadata": {}
                }
            
            image_data = session.resolve_image_identifier(image_identifier)
            if not image_data:
                logger.error(f"edit_image: 未找到标识符对应的图片: {image_identifier}")
                return {
                    "success": False,
                    "content": f"未找到图片标识符: {image_identifier}，请确认标识符正确",
                    "images": [],
                    "error": f"未找到图片标识符: {image_identifier}",
                    "metadata": {}
                }
            logger.info(f"edit_image: 解析标识符 {image_identifier} 成功")
        
        image_bytes = await _get_image_bytes(image_data)
        if not image_bytes:
            return {
                "success": False,
                "content": "无法获取原图，请检查图片标识符或数据是否有效",
                "images": [],
                "error": "无法获取原图，请检查图片标识符或数据是否有效",
                "metadata": {}
            }
        
        # 获取原图尺寸并确定输出尺寸
        original_width, original_height = 1024, 1024  # 默认正方形
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                original_width, original_height = img.size
                logger.info(f"原图尺寸: {original_width}x{original_height}")
        except Exception as e:
            logger.warning(f"无法获取原图尺寸，使用默认尺寸: {e}")
        
        # 根据原图比例选择最接近的标准尺寸
        target_size = _get_closest_size(original_width, original_height)
        logger.info(f"选择输出尺寸: {target_size}")
        
        # 转换为 PNG 格式（DALL-E 要求）
        image_bytes = _convert_to_png(image_bytes)
        
        # 构造 multipart 请求
        url = f"{api_base}/images/edits"
        
        async with ClientSession() as http_session:
            form = FormData()
            form.add_field('image', image_bytes, filename='image.png', content_type='image/png')
            form.add_field('prompt', prompt)
            
            # 可选参数
            form.add_field('n', '1')
            form.add_field('size', target_size)
            
            headers = {
                "Authorization": f"Bearer {api_key}"
            }
            
            logger.info(f"调用图片编辑 API: {url}, model: {model}, prompt: {prompt[:50]}...")
            
            async with http_session.post(url, headers=headers, data=form) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    # 截断过长的错误信息用于日志
                    error_text_for_log = error_text[:500] if len(error_text) > 500 else error_text
                    logger.error(f"图片编辑 API 调用失败: {resp.status}, 响应: {error_text_for_log}")
                    return {
                        "success": False,
                        "content": f"API 调用失败: HTTP {resp.status}",
                        "images": [],
                        "error": f"API 调用失败: HTTP {resp.status}, {error_text[:200]}",
                        "metadata": {}
                    }
                
                result = await resp.json()
        
        # 调试日志：记录 API 返回结果（截断可能的 base64 数据）
        result_for_log = str(result)
        if len(result_for_log) > 500:
            result_for_log = result_for_log[:500] + "...[截断]"
        logger.info(f"图片编辑 API 返回: {result_for_log}")
        
        if not result:
            logger.error("图片编辑 API 返回空结果")
            return {
                "success": False,
                "content": "API 返回空结果",
                "images": [],
                "error": "API 返回空结果",
                "metadata": {}
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
            error_info = result.get("error", {})
            error_msg = error_info.get("message", "无法从 API 响应中提取图片 URL") if error_info else "无法从 API 响应中提取图片 URL"
            logger.error(f"无法从响应中提取图片 URL: {result}")
            return {
                "success": False,
                "content": f"图片编辑失败: {error_msg}",
                "images": [],
                "error": error_msg,
                "metadata": {}
            }
        
        logger.info(f"成功编辑图片，生成 {len(urls)} 张")
        
        # ===== 标准化返回格式 =====
        # 存储新图片到 AI 图片列表
        identifiers = []
        if session:
            for url in urls:
                identifier = session.store_ai_image(url)
                identifiers.append(identifier)
                logger.info(f"edit_image: 存储新图片 {identifier}")
        
        if identifiers:
            if len(identifiers) == 1:
                content = f"已成功编辑图片，生成 {identifiers[0]}。"
            else:
                id_str = ", ".join(identifiers)
                content = f"已成功编辑图片，生成 {len(identifiers)} 张：{id_str}。"
        else:
            content = f"已成功编辑图片，生成 {len(urls)} 张"
        
        return {
            "success": True,
            "content": content,
            "images": urls,  # 编辑后的真实图片
            "error": None,
            "metadata": {
                "identifiers": identifiers,
                "model": model,
                "prompt": prompt,
                "n": len(urls)
            }
        }
        
    except Exception as e:
        logger.exception(f"编辑图片失败: {e}")
        return {
            "success": False,
            "content": f"图片编辑失败: {str(e)}",
            "images": [],
            "error": str(e),
            "metadata": {}
        }
