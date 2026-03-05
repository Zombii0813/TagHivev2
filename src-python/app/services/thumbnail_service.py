"""缩略图服务"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import logging
import os
from typing import Optional

from PIL import Image

from ..config import settings

logger = logging.getLogger(__name__)

# 缩略图配置
DEFAULT_QUALITY = 80
THUMBNAIL_SIZES = {
    "small": (100, 100),
    "medium": (200, 200),
    "large": (400, 400),
}


@dataclass
class ThumbnailService:
    """缩略图服务"""
    
    thumbs_dir: Path = field(default_factory=lambda: Path(settings.thumbs_dir))
    
    def __post_init__(self):
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)
    
    def get_thumbnail_path(self, file_path: str, size: str = "medium") -> Path:
        """获取缩略图路径"""
        file_hash = hashlib.sha256(file_path.encode()).hexdigest()[:16]
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
            
            if ext in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}:
                return self._generate_image_thumbnail(path, thumb_path, size)
            elif ext in {".mp4", ".mov", ".avi", ".mkv"}:
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
        """生成图片缩略图"""
        try:
            with Image.open(source) as img:
                # 转换为 RGB（处理透明图片）
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                # 计算缩略图尺寸
                target_size = THUMBNAIL_SIZES.get(size, THUMBNAIL_SIZES["medium"])
                img.thumbnail(target_size, Image.Resampling.LANCZOS)
                
                # 保存
                if self._is_webp_supported():
                    img.save(target, "WEBP", quality=DEFAULT_QUALITY)
                else:
                    img.save(target, "JPEG", quality=DEFAULT_QUALITY)
                
                return f"file://{target}"
                
        except Exception as e:
            logger.error(f"Failed to generate image thumbnail: {e}")
            return None
    
    def _generate_video_thumbnail(
        self, 
        source: Path, 
        target: Path,
        size: str
    ) -> Optional[str]:
        """生成视频缩略图（使用 FFmpeg）"""
        import subprocess
        
        try:
            target_size = THUMBNAIL_SIZES.get(size, THUMBNAIL_SIZES["medium"])
            
            # 使用 FFmpeg 提取第一帧
            cmd = [
                "ffmpeg",
                "-i", str(source),
                "-ss", "00:00:01",  # 第1秒
                "-vframes", "1",
                "-vf", f"scale={target_size[0]}:{target_size[1]}:force_original_aspect_ratio=decrease",
                "-y",
                str(target)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and target.exists():
                return f"file://{target}"
            else:
                logger.warning(f"FFmpeg failed: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg timeout for {source}")
            return None
        except FileNotFoundError:
            logger.warning("FFmpeg not found, skipping video thumbnail")
            return None
        except Exception as e:
            logger.error(f"Failed to generate video thumbnail: {e}")
            return None
    
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
