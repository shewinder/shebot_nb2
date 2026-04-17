"""
Session 图像存储核心层（纯工具模块，不依赖 hoshino）

供 bot 代码和 Skill 脚本共用。Skill 脚本可安全 import 而不触发 NoneBot 初始化。
"""
import base64
import json
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
        data/aichat/images/{session_id}/
            ├── .meta.json
            ├── user_image_1.png
            └── ai_image_1.jpg
    """

    BASE_DIR: Path = Path("data/aichat/images")

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._dir = self.BASE_DIR / session_id
        self._meta_file = self._dir / ".meta.json"
        self._memory_fallback: Dict[str, str] = {}
        self._ensure_dir()
        self._meta: Dict[str, Dict[str, Any]] = self._load_meta()

    def _ensure_dir(self) -> None:
        """确保存储目录存在"""
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
            with open(self._meta_file, "w", encoding="utf-8") as f:
                json.dump(self._meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[ImageStoreCore] 保存 .meta.json 失败: {e}")

    def _next_index(self, source: str) -> int:
        """计算下一个序号"""
        prefix = f"{source}_image_"
        max_idx = 0
        for key in self._meta.keys():
            if key.startswith(prefix):
                try:
                    idx = int(key[len(prefix):])
                    max_idx = max(max_idx, idx)
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

    def store_bytes(self, data: bytes, source: str, ext: str = "png") -> ImageEntry:
        """存储图像字节数据

        Args:
            data: 图像原始字节数据
            source: "user" 或 "ai"
            ext: 文件扩展名（默认 png）

        Returns:
            ImageEntry
        """
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
        )
        self._meta[entry.identifier.lstrip("<").rstrip(">")] = entry.to_dict()
        self._save_meta()
        self.cleanup()

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
        return None

    def get_data_url(self, identifier: str) -> Optional[str]:
        """根据标识符获取 base64 data URL"""
        clean_id = identifier.lstrip("<").rstrip(">")

        # 1. 尝试从文件读取
        if clean_id in self._meta:
            try:
                entry = ImageEntry.from_dict(self._meta[clean_id])
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
        """列出所有图像"""
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
        """清理超限图像，保留最新的"""
        all_entries = self.list_all()
        if len(all_entries) <= max_images:
            return

        to_remove = all_entries[:len(all_entries) - max_images]
        for entry in to_remove:
            try:
                clean_id = entry.identifier.lstrip("<").rstrip(">")
                self._meta.pop(clean_id, None)
                if entry.file_path.exists():
                    entry.file_path.unlink()
                    logger.debug(f"[ImageStoreCore] 清理旧图像: {entry.identifier}")
            except Exception:
                pass
        self._save_meta()
