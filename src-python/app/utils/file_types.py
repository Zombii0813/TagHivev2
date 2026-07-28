from __future__ import annotations

from pathlib import Path

# 文件类型分类的唯一权威来源（single source of truth）。
# media_info、缩略图服务等模块统一从此处导入，避免各处维护分歧的扩展名列表。
# 扩展名一律小写、不含前导点。

# 图片
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff"}

# 视频：常见容器 + 不常见容器（ts/m2ts 等）。
# 只要 PyAV/FFmpeg 能解码，缩略图与时长提取即可支持；不能解码的会静默跳过。
VIDEO_EXTENSIONS = {
    # 常见
    "mp4", "mov", "mkv", "avi", "wmv", "flv", "webm", "m4v",
    "mpg", "mpeg", "3gp",
    # 不常见 / 专业格式
    "ts", "m2ts", "mts",   # MPEG 传输流 / AVCHD
    "m2v",                  # MPEG-2 视频基本流
    "vob",                  # DVD
    "rmvb", "rm",           # RealMedia
    "asf",                  # Advanced Systems Format
    "ogv",                  # Ogg 视频
    "divx",                 # DivX
    "f4v",                  # Flash
    "mxf",                  # 广电素材交换格式
    "dav",                  # 部分监控设备录像
}

# 文档
DOC_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt"}

# 音频
AUDIO_EXTENSIONS = {"mp3", "wav", "flac", "aac", "ogg", "m4a", "wma", "opus"}

# 浏览器/WebView2 原生 <video> 可直接播放的视频容器（无需服务端转码）。
# 其余视频格式（如 ts/rmvb/wmv/vob）需经 /transcode 端点转封装或转码为 fMP4 才能在线播放。
# 注：mp4/mov/m4v 通常为 H.264+AAC 可原生播放；极少数非常规编码由前端 error 回退兜底。
NATIVE_PLAYABLE_EXTENSIONS = {"mp4", "webm", "ogg", "ogv", "mov", "m4v"}


def classify_file(path: Path) -> str:
    """根据扩展名将文件归类为 image/video/doc/audio/other。

    Args:
        path: 文件路径。

    Returns:
        分类字符串，取值为 "image"、"video"、"doc"、"audio" 或 "other"。
    """
    ext = path.suffix.lower().lstrip(".")
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in DOC_EXTENSIONS:
        return "doc"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    return "other"
