"""
环境信息工具
提供获取当前时间等功能
"""
from datetime import datetime
from typing import Annotated, Any, Dict, Literal

from pydantic import Field

from ..registry import tool_registry, ok


@tool_registry.register(
    description="""获取当前准确时间。

当你需要以下场景时调用：
- 需要当前准确时间作为参考

注意：这是获取准确时间的唯一方式，System 消息中不包含当前时间。""",
)
async def get_current_time(
    format: Annotated[
        Literal["full", "time", "date", "timestamp"],
        Field(description="返回格式：full(完整日期时间)、time(仅时间)、date(仅日期)、timestamp(Unix时间戳秒数)"),
    ] = "full",
) -> Dict[str, Any]:
    """获取当前时间
    
    Args:
        format: 返回格式
        
    Returns:
        包含当前时间的 ToolResult
    """
    now = datetime.now()
    
    formats = {
        "full": now.strftime("%Y-%m-%d %H:%M:%S"),
        "time": now.strftime("%H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": str(int(now.timestamp()))
    }
    
    time_str = formats.get(format, formats["full"])
    
    return ok(
        content=f"当前时间：{time_str}",
        metadata={
            "time": time_str,
            "format": format,
            "timestamp": int(now.timestamp()),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "hour": now.hour,
            "minute": now.minute,
            "second": now.second,
            "weekday": now.strftime("%A")
        }
    )
