"""
视频存储核心（Session 级，与 _image_store_core.py 对齐）

Skill 脚本直接使用本类以避免 NoneBot 初始化；Session 层通过
session.py 的轻量封装访问。存储目录与图片分开：
    data/aichat/videos/{session_id}/
"""
import base64
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("video_store_core")

# 视频存储根目录（与 _image_store_core.BASE_DIR 同级，优先使用 PROJECT_ROOT 环境变量）
BASE_DIR: Path = Path(os.environ.get("PROJECT_ROOT", ".")).resolve() / "data" / "aichat" / "videos"


@dataclass
class VideoEntry:
    """视频条目元数据"""
    identifier: str          # 如 "<ai_video_1>"
    source: str              # "user" 或 "ai"
    session_id: str
    filename: str
    format: str = "mp4"
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: int = 0
    created_at: float = 0.0
    file_path: Path = field(default_factory=Path)
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identifier": self.identifier,
            "source": self.source,
            "session_id": self.session_id,
            "filename": self.filename,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "file_path": str(self.file_path),
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoEntry":
        return cls(
            identifier=data.get("identifier", ""),
            source=data.get("source", "ai"),
            session_id=data.get("session_id", ""),
            filename=data.get("filename", ""),
            format=data.get("format", "mp4"),
            width=data.get("width"),
            height=data.get("height"),
            size_bytes=data.get("size_bytes", 0),
            created_at=data.get("created_at", 0.0),
            file_path=Path(data.get("file_path", "")),
            url=data.get("url"),
        )


class VideoStoreCore:
    """会话级视频存储（同步实现，供 Skill 脚本调用）"""

    MAX_ENTRIES = 32          # 每会话最多保留视频数
    MAX_TOTAL_BYTES = 1 << 30  # 每会话视频总大小上限 1GB

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._dir = BASE_DIR / session_id
        self._meta_file = self._dir / ".meta.json"
        self._lock = threading.Lock()
        self._memory_fallback: Dict[str, str] = {}
        # 惰性建目录：会话创建不再急切 mkdir（与 _image_store_core 对齐），
        # 仅在 store_bytes/_save_meta 真正写入时创建
        self._meta = self._load_meta()

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _load_meta(self) -> Dict[str, Any]:
        if not self._meta_file.exists():
            return {}
        try:
            return json.loads(self._meta_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[VideoStoreCore] meta 读取失败: {e}")
            return {}

    def _save_meta(self) -> None:
        try:
            self._ensure_dir()
            tmp = self._meta_file.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._meta, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._meta_file)
        except Exception as e:
            logger.warning(f"[VideoStoreCore] meta 写入失败: {e}")

    def _next_index(self, source: str) -> int:
        """从磁盘重读计算下一个序号（跨进程一致）"""
        prefix = f"{source}_video_"
        max_idx = 0
        for name in self._meta:
            if name.startswith(prefix):
                try:
                    max_idx = max(max_idx, int(name.rsplit("_", 1)[1]))
                except Exception:
                    pass
        return max_idx + 1

    def _cleanup_locked(self) -> None:
        """超出数量/大小上限时删除最旧条目"""
        entries = sorted(
            self._meta.values(), key=lambda d: d.get("created_at", 0))
        total = sum(d.get("size_bytes", 0) for d in self._meta.values())
        removed = 0
        for data in entries:
            if len(self._meta) - removed <= self.MAX_ENTRIES and total <= self.MAX_TOTAL_BYTES:
                break
            try:
                p = Path(data.get("file_path", ""))
                if p.exists():
                    p.unlink()
            except Exception:
                pass
            self._meta.pop(data["identifier"].lstrip("<").rstrip(">"), None)
            removed += 1

    def store_bytes(self, data: bytes, source: str, ext: str = "mp4", url: Optional[str] = None) -> VideoEntry:
        """存储视频字节数据，返回 VideoEntry"""
        with self._lock:
            self._ensure_dir()
            use_ext = ext if ext in ("mp4", "webm", "gif") else "mp4"
            idx = self._next_index(source)
            filename = f"{source}_video_{idx}.{use_ext}"
            identifier = f"<{source}_video_{idx}>"
            file_path = self._dir / filename

            try:
                with open(file_path, "wb") as f:
                    f.write(data)
            except Exception as e:
                logger.error(f"[VideoStoreCore] 写入文件失败: {e}，降级为内存存储")
                b64 = base64.b64encode(data).decode("utf-8")
                self._memory_fallback[identifier] = f"data:video/{use_ext};base64,{b64}"
                return VideoEntry(
                    identifier=identifier, source=source, session_id=self.session_id,
                    filename="", format=use_ext, size_bytes=len(data),
                    created_at=time.time(), file_path=Path(""), url=url,
                )

            entry = VideoEntry(
                identifier=identifier, source=source, session_id=self.session_id,
                filename=filename, format=use_ext, size_bytes=len(data),
                created_at=time.time(), file_path=file_path.resolve(), url=url,
            )
            self._meta[identifier.lstrip("<").rstrip(">")] = entry.to_dict()
            self._cleanup_locked()
            self._save_meta()
            logger.info(f"[VideoStoreCore] 存储视频 {identifier} -> {file_path}, {len(data)} bytes")
            return entry

    def get(self, identifier: str) -> Optional[VideoEntry]:
        clean_id = identifier.lstrip("<").rstrip(">")
        if clean_id in self._meta:
            try:
                return VideoEntry.from_dict(self._meta[clean_id])
            except Exception:
                pass
        self._meta = self._load_meta()
        if clean_id in self._meta:
            try:
                return VideoEntry.from_dict(self._meta[clean_id])
            except Exception:
                pass
        return None

    def get_file_path(self, identifier: str) -> Optional[Path]:
        entry = self.get(identifier)
        if entry and entry.file_path.exists():
            return entry.file_path
        return None

    def clear(self) -> None:
        """清空当前会话所有视频，并删除空目录（best-effort，与图片存储对齐）"""
        with self._lock:
            for data in list(self._meta.values()):
                try:
                    p = Path(data.get("file_path", ""))
                    if p.exists():
                        p.unlink()
                except Exception:
                    pass
            self._meta.clear()
            try:
                if self._meta_file.exists():
                    self._meta_file.unlink()
            except Exception:
                pass
            try:
                self._dir.rmdir()
            except OSError:
                pass
            logger.info(f"[VideoStoreCore] 清空会话 {self.session_id} 视频缓存")

    def list_all(self) -> List[VideoEntry]:
        self._meta = self._load_meta()
        results = []
        for data in self._meta.values():
            try:
                results.append(VideoEntry.from_dict(data))
            except Exception:
                pass
        return sorted(results, key=lambda e: e.created_at)
