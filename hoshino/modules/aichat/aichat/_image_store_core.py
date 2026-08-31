"""
Session 图像存储核心层（纯工具模块，不依赖 hoshino）

供 bot 代码和 Skill 脚本共用。Skill 脚本可安全 import 而不触发 NoneBot 初始化。
"""
import base64
import json
import os
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from loguru import logger
except ImportError:
    # 当 loguru 不可用时提供占位实现
    class _FakeLogger:
        def info(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): pass
        def debug(self, msg): pass
    logger = _FakeLogger()

try:
    from PIL import Image as PILImage
    from io import BytesIO
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


@dataclass
class ImageEntry:
    """图像元数据条目"""
    identifier: str          # 如 "<user_image_1>"
    source: str              # "user" | "ai"
    session_id: str
    filename: str            # 磁盘文件名，如 "user_image_1.png"
    format: str              # "png" | "jpg" | "webp" | "gif"
    width: Optional[int]
    height: Optional[int]
    size_bytes: int
    created_at: float
    file_path: Path          # 绝对路径
    url: Optional[str] = None  # 原始来源 URL（QQ 图片、工具下载等），无 URL 时为空

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（file_path 转为字符串）"""
        d = asdict(self)
        d["file_path"] = str(self.file_path)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImageEntry":
        """从字典反序列化"""
        data = dict(data)
        data["file_path"] = Path(data["file_path"])
        return cls(**data)


class ImageStoreCore:
    """会话级图像存储核心管理器

    每个 session 拥有独立的存储目录：
        data/aichat/sessions/{session_id}/images/
            ├── .meta.json
            ├── user_image_1.png
            └── ai_image_1.jpg
    """

    BASE_DIR: Path = Path(os.environ.get("PROJECT_ROOT", ".")).resolve() / "data" / "aichat" / "sessions"

    def __init__(self, session_id: str):
        if not session_id or Path(session_id).name != session_id or session_id in {".", ".."}:
            raise ValueError(f"非法 session_id: {session_id!r}")
        self.session_id = session_id
        self._session_dir = self._resolve_session_dir(session_id)
        self._dir = self._session_dir / "images"
        self._meta_file = self._dir / ".meta.json"
        self._memory_fallback: Dict[str, str] = {}
        # 串行化本实例内的并发存取（并行工具调用同时存图时序号/元数据不互相覆盖）；
        # 跨进程一致性仍由 _next_index 每次从磁盘重读保证
        self._lock = threading.Lock()
        # 惰性建目录：会话创建不再急切 mkdir，首次 store/_save_meta 时才建，
        # 从未存图的会话不会在 data/aichat/sessions 留下空目录
        self._meta: Dict[str, Dict[str, Any]] = self._load_meta()

    @classmethod
    def _resolve_session_dir(cls, session_id: str) -> Path:
        """解析当前会话根目录；子进程可通过环境变量显式传入同一目录"""
        base_dir = cls.BASE_DIR.resolve()
        configured = os.environ.get("AICHAT_SESSION_DIR")
        if configured:
            candidate = Path(configured).resolve()
            try:
                candidate.relative_to(base_dir)
            except ValueError:
                pass
            else:
                if candidate.name == session_id:
                    return candidate
        return base_dir / session_id

    def _ensure_dir(self) -> None:
        """确保存储目录存在（仅在真正写入时调用）"""
        self._dir.mkdir(parents=True, exist_ok=True)

    def _load_meta(self) -> Dict[str, Dict[str, Any]]:
        """加载 .meta.json"""
        if self._meta_file.exists():
            try:
                with open(self._meta_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"[ImageStoreCore] 加载 .meta.json 失败: {e}")
        return {}

    def _save_meta(self) -> None:
        """保存 .meta.json"""
        try:
            self._ensure_dir()
            with open(self._meta_file, "w", encoding="utf-8") as f:
                json.dump(self._meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[ImageStoreCore] 保存 .meta.json 失败: {e}")

    def _next_index(self, source: str) -> int:
        """计算下一个序号——每次从 .meta.json 读取，保证跨进程一致"""
        self._load_meta()
        prefix = f"{source}_image_"
        max_idx = 0
        for key in self._meta.keys():
            if key.startswith(prefix):
                try:
                    max_idx = max(max_idx, int(key[len(prefix):]))
                except ValueError:
                    pass
        return max_idx + 1

    def _extract_meta_from_bytes(self, data: bytes) -> tuple:
        """用 PIL 提取图像元数据，返回 (format, width, height)"""
        fmt = None
        width = None
        height = None
        if _HAS_PIL:
            try:
                img = PILImage.open(BytesIO(data))
                fmt = img.format.lower() if img.format else "png"
                width, height = img.size
            except Exception:
                pass
        return fmt or "png", width, height

    def store_bytes(self, data: bytes, source: str, ext: str = "png", url: Optional[str] = None) -> ImageEntry:
        """存储图像字节数据

        Args:
            data: 图像原始字节数据
            source: "user" 或 "ai"
            ext: 文件扩展名（默认 png）

        Returns:
            ImageEntry
        """
        with self._lock:
            # 惰性建目录：仅在真正存储时创建
            self._ensure_dir()
            # 提取元数据
            img_format, width, height = self._extract_meta_from_bytes(data)
            use_ext = ext if ext in ("png", "jpg", "jpeg", "webp", "gif") else (img_format or "png")
            if use_ext == "jpeg":
                use_ext = "jpg"

            # 确定文件名
            idx = self._next_index(source)
            filename = f"{source}_image_{idx}.{use_ext}"
            identifier = f"<{source}_image_{idx}>"
            file_path = self._dir / filename

            # 写入文件（失败则降级）
            try:
                with open(file_path, "wb") as f:
                    f.write(data)
            except Exception as e:
                logger.error(f"[ImageStoreCore] 写入文件失败: {e}，降级为内存存储")
                b64 = base64.b64encode(data).decode("utf-8")
                self._memory_fallback[identifier] = f"data:image/{use_ext};base64,{b64}"
                return ImageEntry(
                    identifier=identifier,
                    source=source,
                    session_id=self.session_id,
                    filename="",
                    format=img_format or use_ext,
                    width=width,
                    height=height,
                    size_bytes=len(data),
                    created_at=time.time(),
                    file_path=Path(""),
                    url=url,
                )

            # 更新元数据
            entry = ImageEntry(
                identifier=identifier,
                source=source,
                session_id=self.session_id,
                filename=filename,
                format=img_format or use_ext,
                width=width,
                height=height,
                size_bytes=len(data),
                created_at=time.time(),
                file_path=file_path.resolve(),
                url=url,
            )
            self._meta[entry.identifier.lstrip("<").rstrip(">")] = entry.to_dict()
            # 清理超限旧图后统一落盘一次（meta 读写从 2读2写 降为 1读1写）
            self._cleanup_locked()
            self._save_meta()

            logger.info(f"[ImageStoreCore] 存储图像 {identifier} -> {file_path}, {entry.width}x{entry.height}")
            return entry

    def get(self, identifier: str) -> Optional[ImageEntry]:
        """根据标识符获取图像元数据"""
        clean_id = identifier.lstrip("<").rstrip(">")
        if clean_id in self._meta:
            try:
                return ImageEntry.from_dict(self._meta[clean_id])
            except Exception:
                pass
        # 内存未命中：可能由其他进程/实例写入，重新加载 .meta.json
        self._meta = self._load_meta()
        if clean_id in self._meta:
            try:
                return ImageEntry.from_dict(self._meta[clean_id])
            except Exception:
                pass
        return None

    def get_data_url(self, identifier: str) -> Optional[str]:
        """根据标识符获取 base64 data URL"""
        # 1. 尝试从文件读取
        entry = self.get(identifier)
        if entry is not None:
            try:
                if entry.file_path.exists():
                    with open(entry.file_path, "rb") as f:
                        data = f.read()
                    b64 = base64.b64encode(data).decode("utf-8")
                    return f"data:image/{entry.format};base64,{b64}"
            except Exception as e:
                logger.warning(f"[ImageStoreCore] 从文件读取图像失败: {e}")

        # 2. 回退到内存降级存储
        if identifier in self._memory_fallback:
            return self._memory_fallback[identifier]

        return None

    def get_file_path(self, identifier: str) -> Optional[Path]:
        """获取图像的本地文件路径"""
        entry = self.get(identifier)
        if entry and entry.file_path.exists():
            return entry.file_path
        return None

    def list_all(self) -> List[ImageEntry]:
        """列出所有图像（自动刷新 .meta.json）"""
        self._meta = self._load_meta()
        results = []
        for data in self._meta.values():
            try:
                results.append(ImageEntry.from_dict(data))
            except Exception:
                pass
        return sorted(results, key=lambda e: e.created_at)

    def list_by_source(self, source: str) -> List[ImageEntry]:
        """按来源过滤"""
        return [e for e in self.list_all() if e.source == source]

    def cleanup(self, max_images: int = 20) -> None:
        """清理超限图像，保留最新的 max_images 张"""
        with self._lock:
            self._cleanup_locked(max_images)
            self._save_meta()

    def _cleanup_locked(self, max_images: int = 20) -> None:
        """基于内存 meta 清理超限图像（不重读磁盘，落盘由调用方统一执行）"""
        entries = []
        for data in self._meta.values():
            try:
                entries.append(ImageEntry.from_dict(data))
            except Exception:
                pass
        if len(entries) <= max_images:
            return

        entries.sort(key=lambda e: e.created_at)
        to_remove = entries[:len(entries) - max_images]
        for entry in to_remove:
            try:
                clean_id = entry.identifier.lstrip("<").rstrip(">")
                self._meta.pop(clean_id, None)
                if entry.file_path.exists():
                    entry.file_path.unlink()
                    logger.debug(f"[ImageStoreCore] 清理旧图像: {entry.identifier}")
            except Exception:
                pass

    def clear(self) -> None:
        """清空当前会话所有图像（Session 新建/销毁时调用）

        清空后顺手删除空目录（best-effort）：一次性任务会话（子 Agent/后台/
        定时任务）跑完 dispose 后不会在 data/aichat/sessions 留下空目录。
        """
        with self._lock:
            for entry in self._list_entries():
                try:
                    if entry.file_path.exists():
                        entry.file_path.unlink()
                except Exception:
                    pass
            self._meta.clear()
            try:
                if self._meta_file.exists():
                    self._meta_file.unlink()
            except Exception:
                pass
            # 目录内无残留文件时删除自身（rmdir 非空会失败，静默保留）
            try:
                self._dir.rmdir()
            except OSError:
                pass
            logger.info(f"[ImageStoreCore] 清空会话 {self.session_id} 图像缓存")

    def _list_entries(self) -> List[ImageEntry]:
        """解析当前内存 meta 为 ImageEntry 列表（不触发磁盘重读）"""
        results = []
        for data in self._meta.values():
            try:
                results.append(ImageEntry.from_dict(data))
            except Exception:
                pass
        return sorted(results, key=lambda e: e.created_at)
