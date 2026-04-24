"""
Session 图像存储层（异步包装器）

内部使用 ImageStoreCore 处理文件持久化，本层额外提供异步 URL 下载能力。
Skill 脚本应直接使用 image_store_core.ImageStoreCore 以避免 NoneBot 初始化。
"""
import base64
from pathlib import Path
from typing import List, Optional

from loguru import logger

from hoshino.util import aiohttpx

from ._image_store_core import ImageEntry, ImageStoreCore

__all__ = ["ImageStore", "ImageEntry"]


class ImageStore:
    """会话级图像存储管理器（异步包装器）

    每个 session 拥有独立的存储目录：
        data/aichat/images/{session_id}/
    """

    BASE_DIR: Path = ImageStoreCore.BASE_DIR

    def __init__(self, session_id: str):
        self._core = ImageStoreCore(session_id)

    async def _download_url(self, url: str) -> Optional[bytes]:
        """下载 URL 内容为 bytes"""
        try:
            resp = await aiohttpx.get(url)
            if resp.ok:
                return resp.content
            logger.warning(f"[ImageStore] 下载图片失败: HTTP {resp.status_code}, URL={url}")
        except Exception as e:
            logger.warning(f"[ImageStore] 下载图片异常: {e}, URL={url}")
        return None

    @staticmethod
    def _parse_data_url(image_data: str) -> tuple:
        """解析 base64 data URL，返回 (mime_type, base64_data)"""
        if not image_data.startswith("data:"):
            return None, None
        header, _, b64 = image_data.partition(",")
        mime = header[len("data:"):].split(";")[0].strip()
        return mime, b64

    async def store(self, image_data: str, source: str) -> ImageEntry:
        """存储图像（支持 base64 data URL / http URL / 纯 base64）

        Args:
            image_data: base64 data URL 或 http URL 或纯 base64 字符串
            source: "user" 或 "ai"

        Returns:
            ImageEntry
        """
        raw_bytes: Optional[bytes] = None
        ext = "png"

        if image_data.startswith("data:"):
            mime, b64 = self._parse_data_url(image_data)
            if b64:
                try:
                    raw_bytes = base64.b64decode(b64)
                    if mime:
                        ext = mime.split("/")[-1]
                        if ext == "jpeg":
                            ext = "jpg"
                except Exception:
                    pass
        elif image_data.startswith(("http://", "https://")):
            raw_bytes = await self._download_url(image_data)
        else:
            try:
                raw_bytes = base64.b64decode(image_data)
            except Exception:
                pass

        if raw_bytes is None:
            logger.error("[ImageStore] 无法解析图像数据")
            # 降级：让 core 存储空数据（会生成一个空文件，但至少不崩溃）
            raw_bytes = b""

        return self._core.store_bytes(raw_bytes, source, ext)

    def get(self, identifier: str) -> Optional[ImageEntry]:
        return self._core.get(identifier)

    def get_data_url(self, identifier: str) -> Optional[str]:
        return self._core.get_data_url(identifier)

    def get_file_path(self, identifier: str) -> Optional[Path]:
        return self._core.get_file_path(identifier)

    def list_all(self) -> List[ImageEntry]:
        return self._core.list_all()

    def list_by_source(self, source: str) -> List[ImageEntry]:
        return self._core.list_by_source(source)

    def cleanup(self, max_images: int = 20) -> None:
        self._core.cleanup(max_images)

    def clear(self) -> None:
        self._core.clear()
