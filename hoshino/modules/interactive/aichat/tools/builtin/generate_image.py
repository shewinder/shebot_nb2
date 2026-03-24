"""
AI 工具：图片生成
根据文本描述生成图片
"""
from typing import Any, Dict
from loguru import logger

from hoshino.util import aiohttpx

from ..registry import tool_registry


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
            "size": {
                "type": "string",
                "description": "图片尺寸，可选值：1024x1024 (方形), 1024x1792 (竖屏), 1792x1024 (横屏)。默认 1024x1024。",
                "enum": ["1024x1024", "1024x1792", "1792x1024"]
            },
            "quality": {
                "type": "string",
                "description": "图片质量，可选值：standard (标准), hd (高清)。默认 standard。",
                "enum": ["standard", "hd"]
            },
            "n": {
                "type": "integer",
                "description": "生成图片数量，范围 1-4。默认 1。",
                "minimum": 1,
                "maximum": 4
            }
        },
        "required": ["prompt"]
    }
)
async def generate_image(
    prompt: str,
    size: str = "1024x1024",
    quality: str = "standard",
    n: int = 1,
    provider: str = "pollinations"
) -> Dict[str, Any]:
    """
    生成图片
    
    Args:
        prompt: 图片描述
        size: 图片尺寸
        quality: 图片质量
        n: 生成数量
        provider: 生图服务提供商 (pollinations, pollinations-enhanced)
    
    Returns:
        {"success": bool, "urls": List[str], "error": str}
    """
    try:
        # 解析尺寸
        if "x" in size:
            width, height = map(int, size.split("x"))
        else:
            width, height = 1024, 1024
        
        urls = []
        for i in range(n):
            # 使用 Pollinations.ai（免费，无需 API Key）
            # 添加随机种子确保不同图片
            seed = i + 1
            
            if provider == "pollinations-enhanced":
                # 使用增强版（质量更好）
                encoded_prompt = prompt.replace(" ", "%20")
                url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&seed={seed}&nologo=true&enhance=true"
            else:
                # 使用标准版
                encoded_prompt = prompt.replace(" ", "%20")
                url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&seed={seed}&nologo=true"
            
            urls.append(url)
            logger.info(f"生成图片 URL: {url}")
        
        return {
            "success": True,
            "urls": urls,
            "error": None,
            "provider": provider,
            "prompt": prompt,
            "size": size
        }
    except Exception as e:
        logger.exception(f"生成图片失败: {e}")
        return {
            "success": False,
            "urls": [],
            "error": str(e)
        }
