"""统一缩略图缓存身份和原子写入。"""

import hashlib
import os
from pathlib import Path
import uuid


def thumbnail_identity(file_path: str) -> str:
    """依据源路径、纳秒时间及文件大小生成缓存键。"""
    path = Path(file_path)
    try:
        stat = path.stat()
        version = f"{stat.st_mtime_ns}:{stat.st_ctime_ns}:{stat.st_size}"
    except OSError:
        version = "missing"
    return hashlib.sha256(f"v3:{path.resolve()}:{version}".encode()).hexdigest()[:24]


def atomic_image_save(image, target: Path, image_format: str, **options) -> None:
    """先写独立临时文件，再原子替换，避免读到半张缩略图。"""
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        image.save(temporary, image_format, **options)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
