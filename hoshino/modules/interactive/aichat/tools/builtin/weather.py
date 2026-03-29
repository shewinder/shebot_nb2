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
    """根据城市名称获取城市编码
    
    Args:
        city_name: 城市名称，如"北京"
        api_key: 高德地图 API Key
        
    Returns:
        城市编码，失败返回 None
    """
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


async def _get_weather(city: str, api_key: str, extensions: str = "base") -> Optional[Dict[str, Any]]:
    """获取天气信息
    
    Args:
        city: 城市编码或城市名称
        api_key: 高德地图 API Key
        extensions: base(实况) 或 all(预报)
        
    Returns:
        天气数据字典，失败返回 None
    """
    url = "https://restapi.amap.com/v3/weather/weatherInfo"
    
    # 判断是否为城市编码（6位数字）
    city_code = city if city.isdigit() and len(city) == 6 else None
    
    # 如果不是城市编码，先获取编码
    if not city_code:
        city_code = await _get_city_code(city, api_key)
        if not city_code:
            return None
    
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
        if data.get("status") != "1":
            logger.error(f"获取天气失败: {data.get('info', '未知错误')}")
            return None
        
        return data
    except Exception as e:
        logger.exception(f"获取天气异常: {e}")
        return None


def _format_weather(data: Dict[str, Any], extensions: str) -> str:
    """格式化天气信息为易读文本
    
    Args:
        data: API 返回的天气数据
        extensions: base 或 all
        
    Returns:
        格式化的天气文本
    """
    if extensions == "base":
        # 实况天气
        lives = data.get("lives", [])
        if not lives:
            return "暂无天气数据"
        
        live = lives[0]
        return (
            f"📍 {live.get('province', '')} {live.get('city', '')}\n"
            f"🌡️ 温度: {live.get('temperature', '--')}°C\n"
            f"☁️ 天气: {live.get('weather', '--')}\n"
            f"💨 风向: {live.get('winddirection', '--')}\n"
            f"🌬️ 风力: {live.get('windpower', '--')}\n"
            f"💧 湿度: {live.get('humidity', '--')}%\n"
            f"📊 空气质量: {live.get('reporttime', '--')[:10]} 发布"
        )
    else:
        # 预报天气
        forecasts = data.get("forecasts", [])
        if not forecasts:
            return "暂无预报数据"
        
        forecast = forecasts[0]
        city = f"{forecast.get('province', '')} {forecast.get('city', '')}"
        casts = forecast.get("casts", [])
        
        lines = [f"📍 {city} 未来天气预报\n"]
        
        for cast in casts[:3]:  # 最多显示3天
            date = cast.get('date', '--')
            week = cast.get('week', '--')
            day_weather = cast.get('dayweather', '--')
            night_weather = cast.get('nightweather', '--')
            day_temp = cast.get('daytemp', '--')
            night_temp = cast.get('nighttemp', '--')
            day_wind = cast.get('daywind', '--')
            night_wind = cast.get('nightwind', '--')
            
            # 周转换
            week_map = {'1': '周一', '2': '周二', '3': '周三', '4': '周四', '5': '周五', '6': '周六', '7': '周日'}
            week_str = week_map.get(str(week), week)
            
            lines.append(
                f"📅 {date} {week_str}\n"
                f"  ☁️ {day_weather} / {night_weather}\n"
                f"  🌡️ {night_temp}°C ~ {day_temp}°C\n"
                f"  💨 {day_wind}风"
            )
        
        return "\n".join(lines)


@tool_registry.register(
    name="get_weather",
    description="""查询指定城市的天气信息。

支持查询实时天气和未来几天预报，城市名称支持中文（如"北京"、"上海"、"广州"等）。

使用场景：
- 用户询问"今天天气怎么样"、"北京明天天气如何"
- 用户关心出行天气、穿衣建议
- 用户需要了解某地的气候情况

注意：
- 城市名称可以是"北京"、"上海市"等常见名称
- 预报模式会返回未来3天的天气预报""",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称，如\"北京\"、\"上海\"、\"广州\"等"
            },
            "forecast": {
                "type": "boolean",
                "description": "是否获取天气预报，true 返回未来几天预报，false 返回实时天气（默认）"
            }
        },
        "required": ["city"]
    },
)
async def get_weather(city: str, forecast: bool = False) -> Dict[str, Any]:
    """查询天气信息
    
    Args:
        city: 城市名称
        forecast: 是否获取预报，默认 False（实时天气）
        
    Returns:
        工具调用结果
    """
    try:
        # 获取高德 API Key
        gaode_key = getattr(conf, 'gaode_api_key', '')
        if not gaode_key:
            return fail("天气服务未配置，请联系管理员设置高德地图 API Key")
        
        # 获取天气数据
        extensions = "all" if forecast else "base"
        data = await _get_weather(city, gaode_key, extensions)
        
        if not data:
            return fail(f"无法获取 {city} 的天气信息，请检查城市名称是否正确")
        
        # 格式化天气信息
        weather_text = _format_weather(data, extensions)
        
        return ok(
            weather_text,
            metadata={
                "city": city,
                "forecast": forecast,
                "raw_data": data
            }
        )
        
    except Exception as e:
        logger.exception(f"查询天气失败: {e}")
        return fail(f"查询天气失败: {str(e)}", error=str(e))
