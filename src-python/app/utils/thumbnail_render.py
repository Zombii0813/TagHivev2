"""共用缩略图渲染，统一方向、透明度及缩放。"""

from pathlib import Path
from PIL import Image, ImageOps
from .thumbnail_cache import atomic_image_save

SIZES = {"xs": (80, 80), "small": (120, 120), "medium": (240, 240),
         "large": (480, 480), "xl": (800, 800)}


def fit_and_save(image: Image.Image, target: Path, size: str, webp: bool) -> str:
    """先校正 EXIF 方向，再保持比例缩放并原子保存。

    Args:
        image: 源图像或视频帧。
        target: 目标缓存路径。
        size: 尺寸名称。
        webp: 是否输出 WebP。

    Returns:
        缓存文件 URL。
    """
    image = ImageOps.exif_transpose(image).convert("RGBA")
    bounds = SIZES.get(size, SIZES["medium"])
    image = ImageOps.contain(image, bounds, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", bounds, (32, 32, 32))
    canvas.paste(image, ((bounds[0] - image.width) // 2, (bounds[1] - image.height) // 2), image)
    atomic_image_save(canvas, target, "WEBP" if webp else "JPEG", quality=85)
    return f"file://{target}"
