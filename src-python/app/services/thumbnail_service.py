"""缩略图服务"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import logging
import os
import subprocess
import sys
from typing import Optional, List, Dict, Callable

from PIL import Image

from ..config import settings
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
        """生成图片缩略图 - 统一为正方形，保持清晰度"""
        try:
            with Image.open(source) as img:
                # 转换为 RGB（处理透明图片）
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                # 获取目标尺寸（正方形）
                target_size = THUMBNAIL_SIZES.get(size, THUMBNAIL_SIZES["medium"])
                target_width, target_height = target_size
                
                # 使用高质量缩放，保持原始宽高比
                img.thumbnail((target_width * 2, target_height * 2), Image.Resampling.LANCZOS)
                
                # 创建正方形画布，使用黑色背景填充
                final_img = Image.new("RGB", target_size, (32, 32, 32))
                
                # 计算居中位置
                img_width, img_height = img.size
                scale = min(target_width / img_width, target_height / img_height)
                new_width = int(img_width * scale)
                new_height = int(img_height * scale)
                
                # 高质量缩放
                if new_width != img_width or new_height != img_height:
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # 粘贴到居中位置
                offset_x = (target_width - new_width) // 2
                offset_y = (target_height - new_height) // 2
                final_img.paste(img, (offset_x, offset_y))
                
                # 保存
                if self._is_webp_supported():
                    final_img.save(target, "WEBP", quality=DEFAULT_QUALITY)
                else:
                    final_img.save(target, "JPEG", quality=DEFAULT_QUALITY)
                
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
        """生成视频缩略图（使用 FFmpeg）- 统一为正方形"""
        
        try:
            target_size = THUMBNAIL_SIZES.get(size, THUMBNAIL_SIZES["medium"])
            target_width, target_height = target_size
            
            # 使用 FFmpeg 提取第一帧，保持宽高比并填充到正方形
            # scale=iw*min(w/iw\,h/ih):ih*min(w/iw\,h/ih) - 保持比例缩放
            # pad=w:h:(ow-iw)/2:(oh-ih)/2 - 填充到目标尺寸并居中
            vf_filter = (
                f"scale='iw*min({target_width}/iw\\,{target_height}/ih):"
                f"ih*min({target_width}/iw\\,{target_height}/ih)':"
                f"force_original_aspect_ratio=decrease,"
                f"pad={target_width}:{target_height}:({target_width}-iw)/2:({target_height}-ih)/2:black"
            )
            
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-i", str(source),
                "-ss", "00:00:01",  # 第1秒
                "-vframes", "1",
                "-vf", vf_filter,
                "-y",
                str(target)
            ]
            
            # Windows: 隐藏控制台窗口
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=creationflags
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
