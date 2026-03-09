"""媒体文件信息提取工具"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 视频和音频文件扩展名
VIDEO_EXTENSIONS = {"mp4", "mov", "mkv", "avi", "wmv", "flv", "webm", "m4v", "mpg", "mpeg", "3gp"}
AUDIO_EXTENSIONS = {"mp3", "wav", "flac", "aac", "ogg", "m4a", "wma", "opus"}


def extract_duration(path: Path) -> Optional[float]:
    """提取媒体文件时长（秒）
    
    支持视频和音频文件。如果无法提取或不是媒体文件，返回 None。
    
    Args:
        path: 文件路径
        
    Returns:
        时长（秒），失败返回 None
    """
    ext = path.suffix.lower().lstrip(".")
    
    # 只处理视频和音频文件
    if ext not in VIDEO_EXTENSIONS and ext not in AUDIO_EXTENSIONS:
        return None
    
    try:
        # 尝试使用 pymediainfo
        try:
            from pymediainfo import MediaInfo
            media_info = MediaInfo.parse(str(path))
            for track in media_info.tracks:
                if track.track_type in ("Video", "Audio"):
                    duration = track.duration
                    if duration:
                        # pymediainfo 返回的是毫秒
                        return float(duration) / 1000.0
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"pymediainfo failed for {path}: {e}")
        
        # 备选：尝试使用 ffmpeg
        try:
            import subprocess
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", 
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                duration_str = result.stdout.strip()
                if duration_str:
                    return float(duration_str)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug(f"ffprobe failed for {path}: {e}")
            
    except Exception as e:
        logger.debug(f"Failed to extract duration from {path}: {e}")
    
    return None


def is_media_file(path: Path) -> bool:
    """检查文件是否为媒体文件（视频或音频）
    
    Args:
        path: 文件路径
        
    Returns:
        是否为媒体文件
    """
    ext = path.suffix.lower().lstrip(".")
    return ext in VIDEO_EXTENSIONS or ext in AUDIO_EXTENSIONS
