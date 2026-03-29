"""
AI 工具：天气查询
使用高德地图 API 查询实时天气和天气预报
"""
from typing import Any, Dict, Optional

from loguru import logger

from hoshino.util import aiohttpx

from ..registry import tool_registry, ok, fail
from ...config import Config

# 加载配置
conf = Config.get_instance('aichat')


async def _get_city_code(city_name: str, api_key: str) -> Optional[str]:
    """根据城市名称获取城市编码"""
    url = "https://restapi.amap.com/v3/config/district"
    params = {
        "key": api_key,
        "keywords": city_name,
        "subdistrict": 0,
        "extensions": "base"
    }
    
    try:
        resp = await aiohttpx.get(url, params=params)
        if not resp.ok:
            logger.error(f"获取城市编码失败: {resp.status_code}")
            return None
        
        data = resp.json if hasattr(resp, 'json') else await resp.json()
        logger.debug(f"[Weather Debug] 城市编码响应: {data}")
        if data.get("status") != "1":
            logger.error(f"获取城市编码失败: {data.get('info', '未知错误')}")
            return None
        
        districts = data.get("districts", [])
        if not districts:
            return None
        
        return districts[0].get("adcode")
    except Exception as e:
        logger.exception(f"获取城市编码异常: {e}")
        return None


async def _get_weather_data(city_code: str, api_key: str, extensions: str) -> Optional[Dict[str, Any]]:
    """获取天气数据"""
    url = "https://restapi.amap.com/v3/weather/weatherInfo"
    params = {
        "key": api_key,
        "city": city_code,
        "extensions": extensions
    }
    
    try:
        resp = await aiohttpx.get(url, params=params)
        if not resp.ok:
            logger.error(f"获取天气失败: {resp.status_code}")
            return None
        
        data = resp.json if hasattr(resp, 'json') else await resp.json()
        logger.debug(f"[Weather Debug] 天气API响应 ({extensions}): {data}")
        if data.get("status") != "1":
            logger.error(f"获取天气失败: {data.get('info', '未知错误')}")
            return None
        
        return data
    except Exception as e:
        logger.exception(f"获取天气异常: {e}")
        return None


@tool_registry.register(
    name="get_weather",
    description="""查询指定城市的天气信息，返回当前实时天气和未来几天预报数据。

数据包含两部分：
- current: 当前实时天气（温度、天气状况、风向、风力、湿度等）
- forecast: 未来几天的天气预报（含今天、明天、后天）

使用建议：
- 用户问"现在天气怎么样"：主要参考 current 数据，可结合 forecast 中今天的数据补充
- 用户问"今天天气"：结合 current 和 forecast 中今天的数据
- 用户问"明天/后天天气"：从 forecast 中取对应日期
- 用户问"未来几天天气"：展示 forecast 中所有数据

注意：如果用户只问当前/今天天气，不要主动预报后几天的天气。""",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称，如\"北京\"、\"上海\"、\"广州\"等"
            }
        },
        "required": ["city"]
    },
)
async def get_weather(city: str) -> Dict[str, Any]:
    """查询天气信息"""
    try:
        gaode_key = getattr(conf, 'gaode_api_key', '')
        if not gaode_key:
            return fail("天气服务未配置，请联系管理员设置高德地图 API Key")
        
        # 获取城市编码
        city_code = city if city.isdigit() and len(city) == 6 else await _get_city_code(city, gaode_key)
        if not city_code:
            return fail(f"无法获取 {city} 的城市编码，请检查城市名称是否正确")
        
        # 并发获取当前天气和预报
        import asyncio
        current_task = _get_weather_data(city_code, gaode_key, "base")
        forecast_task = _get_weather_data(city_code, gaode_key, "all")
        
        current_data, forecast_data = await asyncio.gather(current_task, forecast_task, return_exceptions=True)
        
        # 检查是否有成功的结果
        if isinstance(current_data, Exception) and isinstance(forecast_data, Exception):
            return fail(f"获取 {city} 的天气信息失败")
        
        result = {
            "current": current_data if not isinstance(current_data, Exception) else None,
            "forecast": forecast_data if not isinstance(forecast_data, Exception) else None
        }
        
        logger.debug(f"[Weather Debug] 返回给AI的数据: {result}")
        return ok(str(result), metadata={"city": city})
        
    except Exception as e:
        logger.exception(f"查询天气失败: {e}")
        return fail(f"查询天气失败: {str(e)}", error=str(e))
