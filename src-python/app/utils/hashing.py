from __future__ import annotations

from pathlib import Path
import hashlib


def sha256_file(path: Path, chunk_size: int = 8192) -> str | None:
    """计算文件的 SHA256 哈希值
    
    Args:
        path: 文件路径
        chunk_size: 读取块大小
        
    Returns:
        SHA256 哈希字符串，失败返回 None
    """
    try:
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception:
        return None
