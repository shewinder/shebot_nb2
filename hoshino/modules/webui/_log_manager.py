"""
WebUI 插件内部的日志管理模块
完全封装在插件内，不侵入框架
"""
import asyncio
from typing import List
from collections import deque
from loguru import logger


class LogWebSocketManager:
    """管理 WebSocket 日志连接和广播"""
    
    def __init__(self):
        self.active_connections: List = []
        self.log_queue = deque(maxlen=1000)
        self._lock = asyncio.Lock()
        self._sink_id = None
    
    def start(self):
        """启动日志收集，添加 loguru sink"""
        if self._sink_id is None:
            self._sink_id = logger.add(self._log_sink, level="DEBUG", format="{message}")
    
    def stop(self):
        """停止日志收集，移除 sink"""
        if self._sink_id is not None:
            try:
                logger.remove(self._sink_id)
            except:
                pass
            self._sink_id = None
    
    def _log_sink(self, message):
        """loguru sink 回调"""
        try:
            record = message.record
            level = record["level"].name
            module = record["name"].split(".")[0]
            msg = record["message"]
            timestamp = record["time"].strftime("%H:%M:%S")
            
            self.add_log_sync(level, module, msg, timestamp)
        except Exception:
            pass
    
    async def connect(self, websocket):
        """新 WebSocket 连接"""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        # 发送积压日志
        log_snapshot = list(self.log_queue)
        for log_data in log_snapshot:
            try:
                await websocket.send_json(log_data)
            except:
                break
    
    async def disconnect(self, websocket):
        """断开 WebSocket 连接"""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        """广播日志到所有连接"""
        self.log_queue.append(message)
        
        disconnected = []
        async with self._lock:
            connections = self.active_connections.copy()
        
        for connection in connections:
            try:
                await connection.send_json(message)
            except:
                disconnected.append(connection)
        
        for conn in disconnected:
            await self.disconnect(conn)
    
    def add_log_sync(self, level: str, module: str, message: str, timestamp: str):
        """同步添加日志（供 sink 调用）"""
        log_data = {
            "timestamp": timestamp,
            "level": level,
            "module": module,
            "message": message
        }
        self.log_queue.append(log_data)
        
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(self.broadcast(log_data))
        except RuntimeError:
            pass


# 全局实例
log_manager = LogWebSocketManager()
