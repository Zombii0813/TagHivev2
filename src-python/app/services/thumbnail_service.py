"""缩略图服务"""

from __future__ import annotations

from ..utils.thumbnail_render import fit_and_save

from ..utils.thumbnail_cache import thumbnail_identity, atomic_image_save

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import logging
from typing import Optional, List, Dict, Callable

from PIL import Image

from ..config import settings
from ..utils.video_frame import extract_video_frame
from ..utils.file_types import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
# 异步缩略图生成模块（用于高级功能）
# from ..core.async_thumbnail import (
#     AsyncThumbnailGenerator,
#     MultiSizeThumbnailGenerator,
#     ThumbnailPrefetcher,
#     Priority,
#     get_async_thumbnail_generator,
#     shutdown_async_generator,
# )

logger = logging.getLogger(__name__)

# 缩略图配置 - 统一使用正方形尺寸，保持所有缩略图大小一致
DEFAULT_QUALITY = 85
THUMBNAIL_SIZES = {
    "xs": (80, 80),
    "small": (120, 120),
    "medium": (240, 240),
    "large": (480, 480),
    "xl": (800, 800),
}


@dataclass
class ThumbnailService:
    """缩略图服务"""

    thumbs_dir: Path = field(default_factory=lambda: Path(settings.thumbs_dir))

    def __post_init__(self):
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)

    def get_thumbnail_path(self, file_path: str, size: str = "medium") -> Path:
        """获取缩略图路径"""
        file_hash = thumbnail_identity(file_path)
        ext = "webp" if self._is_webp_supported() else "jpg"
        return self.thumbs_dir / f"{file_hash}_{size}.{ext}"

    def generate_thumbnail(
        self,
        file_path: str,
        size: str = "medium",
        force: bool = False
    ) -> Optional[str]:
        """生成缩略图

        Args:
            file_path: 原始文件路径
            size: 尺寸 (small, medium, large)
            force: 强制重新生成

        Returns:
            缩略图 URL，失败返回 None
        """
        thumb_path = self.get_thumbnail_path(file_path, size)

        # 检查是否已存在
        if not force and thumb_path.exists():
            return f"file://{thumb_path}"

        try:
            path = Path(file_path)
            if not path.exists():
                return None

            # 检查文件类型
            ext = path.suffix.lower()

            # 统一复用 file_types 的权威扩展名集合（其元素不含前导点，故去点比较）
            bare_ext = ext.lstrip(".")
            if bare_ext in IMAGE_EXTENSIONS:
                return self._generate_image_thumbnail(path, thumb_path, size)
            elif bare_ext in VIDEO_EXTENSIONS:
                return self._generate_video_thumbnail(path, thumb_path, size)
            else:
                # 不支持生成缩略图的类型
                return None

        except Exception as e:
            logger.error(f"Failed to generate thumbnail for {file_path}: {e}")
            return None

    def _generate_image_thumbnail(
        self,
        source: Path,
        target: Path,
        size: str
    ) -> Optional[str]:
        """生成图片缩略图 - 统一为正方形，保持清晰度"""
        try:
            with Image.open(source) as img:
                return self._fit_and_save(img, target, size)
        except Exception as e:
            logger.error(f"Failed to generate image thumbnail: {e}")
            return None

    def _generate_video_thumbnail(
        self,
        source: Path,
        target: Path,
        size: str
    ) -> Optional[str]:
        """生成视频缩略图（使用 PyAV 在进程内解码首帧，无需系统 ffmpeg）- 统一为正方形"""
        try:
            frame = extract_video_frame(source)
            if frame is None:
                logger.warning(f"无法从视频解码首帧: {source}")
                return None
            return self._fit_and_save(frame, target, size)
        except Exception as e:
            logger.error(f"Failed to generate video thumbnail: {e}")
            return None

    def _fit_and_save(
        self,
        img: Image.Image,
        target: Path,
        size: str
    ) -> Optional[str]:
        """将 PIL 图像拟合到正方形画布并保存为缩略图。

        保持原始宽高比缩放，居中粘贴到黑色背景的正方形画布上，图片与视频缩略图共用。

        Args:
            img: 源 PIL 图像（图片文件或视频解码帧）。
            target: 缩略图输出路径。
            size: 尺寸键（xs/small/medium/large/xl）。

        Returns:
            缩略图 file:// URL，失败返回 None。
        """
        return fit_and_save(img, target, size, self._is_webp_supported())


    def _is_webp_supported(self) -> bool:
        """检查是否支持 WebP"""
        try:
            test_img = Image.new("RGB", (10, 10))
            from io import BytesIO
            buffer = BytesIO()
            test_img.save(buffer, "WEBP")
            return True
        except Exception:
            return False

    def cleanup_cache(self, max_age_days: int = 30) -> int:
        """清理过期缓存

        Args:
            max_age_days: 最大保留天数

        Returns:
            清理的文件数量
        """
        import time

        count = 0
        max_age_seconds = max_age_days * 24 * 60 * 60
        current_time = time.time()

        try:
            for file_path in self.thumbs_dir.iterdir():
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        file_path.unlink()
                        count += 1

            logger.info(f"Cleaned up {count} old thumbnails")
            return count

        except Exception as e:
            logger.error(f"Failed to cleanup cache: {e}")
            return 0

    def get_cache_size(self) -> tuple[int, int]:
        """获取缓存大小

        Returns:
            (文件数量, 总字节数)
        """
        count = 0
        total_size = 0

        try:
            for file_path in self.thumbs_dir.iterdir():
                if file_path.is_file():
                    count += 1
                    total_size += file_path.stat().st_size

        except Exception as e:
            logger.error(f"Failed to get cache size: {e}")

        return count, total_size


# 全局服务实例
_thumbnail_service: Optional[ThumbnailService] = None


def get_thumbnail_service() -> ThumbnailService:
    """获取缩略图服务实例"""
    global _thumbnail_service
    if _thumbnail_service is None:
        _thumbnail_service = ThumbnailService()
    return _thumbnail_service
