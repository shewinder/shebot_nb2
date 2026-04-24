"""
AI 调用工具 - 简洁版
让 AI 能够调用另一个 AI 进行单轮对话
"""
import base64
from typing import Any, Dict, List, Optional

from loguru import logger

from hoshino.config import get_plugin_config_by_name
from hoshino.util import aiohttpx
from ..registry import tool_registry, ok, fail


async def _fetch_image(url: str) -> Optional[str]:
    """下载图片并转为 base64 data URL"""
    try:
        resp = await aiohttpx.get(url, timeout=30)
        if not resp.ok:
            return None
        data = resp.content
        if not data:
            return None
        return f"data:image/jpeg;base64,{base64.b64encode(data).decode()}"
    except Exception as e:
        logger.warning(f"下载图片失败 {url}: {e}")
        return None


@tool_registry.register(
    name="ai_call",
    description="调用 AI 进行单轮对话，支持文本和多模态输入",
    parameters={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "提示词"},
            "images": {"type": "array", "items": {"type": "string"}, "description": "图片URL列表"},
            "system": {"type": "string", "description": "系统提示词"}
        },
        "required": ["prompt"]
    }
)
async def ai_call(
    prompt: str,
    images: Optional[List[str]] = None,
    system: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """调用 AI"""
    
    # 获取配置
    conf = get_plugin_config_by_name("aichat")
    api = conf.get_api_by_name(conf.get_current_api()) if conf else None
    if not api:
        return fail("AI 未配置")
    
    # 构建消息
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    
    if images:
        # 多模态
        parts = []
        for url in images[:3]:
            b64 = await _fetch_image(url)
            if b64:
                # 限制 base64 大小（约1MB），避免超限
                if len(b64) > 1400000:  # 约 1MB base64
                    logger.warning(f"图片过大，跳过: {url}")
                    continue
                parts.append({"type": "image_url", "image_url": {"url": b64}})
                logger.info(f"图片已转换 base64, 大小: {len(b64)} 字符")
            else:
                logger.warning(f"图片下载失败: {url}")
        
        if not parts:
            return fail("所有图片下载/转换失败")
        
        parts.append({"type": "text", "text": prompt})
        messages.append({"role": "user", "content": parts})
        logger.info(f"共 {len(parts)-1} 张图片传入 AI")
    else:
        messages.append({"role": "user", "content": prompt})
    
    # 调用 API
    url = f"{api.api_base.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api.api_key}", "Content-Type": "application/json"}
    payload = {"model": api.model, "messages": messages}
    
    # 使用配置中的参数（如果设置了）
    if api.temperature is not None:
        payload["temperature"] = api.temperature
    if api.max_tokens is not None:
        payload["max_tokens"] = api.max_tokens
    
    try:
        resp = await aiohttpx.post(url, headers=headers, json=payload, timeout=60)
        if not resp.ok:
            err = resp.json if hasattr(resp, 'json') else {"error": getattr(resp, 'text', 'unknown')}
            logger.error(f"AI 调用失败: {resp.status_code}, {err}")
            err_msg = err.get('error', {}).get('message', '未知错误') if isinstance(err, dict) else str(err)
            return fail(f"HTTP {resp.status_code}: {err_msg}")
        
        result = resp.json
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        return ok(content)
        
    except Exception as e:
        logger.exception(f"AI 调用异常: {e}")
        return fail(str(e))
