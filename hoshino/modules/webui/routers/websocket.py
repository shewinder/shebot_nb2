from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

router = APIRouter()


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket 日志流"""
    from .._log_manager import log_manager
    
    await log_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                cmd = json.loads(data)
                if cmd.get("action") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await log_manager.disconnect(websocket)
    except Exception:
        await log_manager.disconnect(websocket)
