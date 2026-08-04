"""媒体文件信息提取工具

统一使用 PyAV（wheel 内置 FFmpeg 动态库）在进程内探测媒体信息，无需依赖系统安装的
ffmpeg/libmediainfo；pymediainfo 与 ffprobe 作为兜底，覆盖 PyAV 无法解析的极少数容器。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 视频和音频文件扩展名 —— 统一复用 file_types 中的权威定义，避免多处分歧
from app.utils.file_types import VIDEO_EXTENSIONS, AUDIO_EXTENSIONS


@dataclass(frozen=True)
class MediaInfoResult:
    """媒体探测结果

    Attributes:
        duration: 时长（秒），无法探测时为 None。
        width: 视频宽度（像素），音频或探测失败时为 None。
        height: 视频高度（像素），音频或探测失败时为 None。
        bitrate: 整体比特率（bps），无法探测时为 None。
    """

    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    bitrate: Optional[int] = None

    @property
    def is_empty(self) -> bool:
        """是否所有字段都未能探测到"""
        return (
            self.duration is None
            and self.width is None
            and self.height is None
            and self.bitrate is None
        )


def extract_media_info(path: Path) -> MediaInfoResult:
    """探测媒体文件的时长、分辨率与比特率。

    仅处理视频/音频扩展名；非媒体文件或全部探测失败时返回空结果（各字段为 None）。
    优先 PyAV，缺字段时用 pymediainfo 补齐，最后按「文件大小 / 时长」估算比特率。

    Args:
        path: 文件路径。

    Returns:
        MediaInfoResult；未能探测到的字段为 None。
    """
    ext = path.suffix.lower().lstrip(".")
    if ext not in VIDEO_EXTENSIONS and ext not in AUDIO_EXTENSIONS:
        return MediaInfoResult()

    result = _probe_with_pyav(path)

    # PyAV 未取到关键字段时用 pymediainfo 补齐（部分容器 PyAV 读不到头信息）
    if result.duration is None or (ext in VIDEO_EXTENSIONS and result.width is None):
        fallback = _probe_with_mediainfo(path)
        result = _merge(result, fallback)

    # 容器未声明比特率时，用文件大小与时长估算（转封装流、部分 TS 流常见）
    if result.bitrate is None and result.duration and result.duration > 0:
        try:
            size = path.stat().st_size
            result = _merge(
                result, MediaInfoResult(bitrate=int(size * 8 / result.duration))
            )
        except OSError:
            pass

    return result


def _probe_with_pyav(path: Path) -> MediaInfoResult:
    """使用 PyAV 探测媒体信息，失败返回空结果。

    Args:
        path: 文件路径。

    Returns:
        探测结果；PyAV 缺失或解析失败时各字段为 None。
    """
    try:
        import av
    except ImportError:
        logger.debug("PyAV (av) 未安装，跳过 PyAV 探测")
        return MediaInfoResult()

    try:
        with av.open(str(path)) as container:
            duration: Optional[float] = None
            if container.duration:
                # container.duration 以 av.time_base（微秒）为单位
                duration = float(container.duration) / av.time_base

            bitrate = int(container.bit_rate) if container.bit_rate else None

            width: Optional[int] = None
            height: Optional[int] = None
            if container.streams.video:
                stream = container.streams.video[0]
                codec_ctx = stream.codec_context
                width = codec_ctx.width or None
                height = codec_ctx.height or None
                # 容器未声明时长时退回视频流自身的时长
                if duration is None and stream.duration and stream.time_base:
                    duration = float(stream.duration * stream.time_base)

            return MediaInfoResult(
                duration=duration, width=width, height=height, bitrate=bitrate
            )
    except Exception as exc:
        logger.debug(f"PyAV 探测失败 {path}: {exc}")
        return MediaInfoResult()


def _probe_with_mediainfo(path: Path) -> MediaInfoResult:
    """使用 pymediainfo 探测媒体信息，失败再退回 ffprobe。

    Args:
        path: 文件路径。

    Returns:
        探测结果；两种方式均不可用时各字段为 None。
    """
    try:
        from pymediainfo import MediaInfo

        media_info = MediaInfo.parse(str(path))
        duration: Optional[float] = None
        width: Optional[int] = None
        height: Optional[int] = None
        bitrate: Optional[int] = None

        for track in media_info.tracks:
            if track.track_type == "General":
                if bitrate is None and track.overall_bit_rate:
                    bitrate = int(track.overall_bit_rate)
                if duration is None and track.duration:
                    duration = float(track.duration) / 1000.0
            elif track.track_type == "Video":
                if width is None and track.width:
                    width = int(track.width)
                if height is None and track.height:
                    height = int(track.height)
                if duration is None and track.duration:
                    duration = float(track.duration) / 1000.0
            elif track.track_type == "Audio":
                if duration is None and track.duration:
                    duration = float(track.duration) / 1000.0

        found = MediaInfoResult(
            duration=duration, width=width, height=height, bitrate=bitrate
        )
        if not found.is_empty:
            return found
    except ImportError:
        pass
    except Exception as exc:
        logger.debug(f"pymediainfo 探测失败 {path}: {exc}")

    return _probe_with_ffprobe(path)


def _probe_with_ffprobe(path: Path) -> MediaInfoResult:
    """使用系统 ffprobe 探测媒体信息（最后兜底），未安装时返回空结果。

    Args:
        path: 文件路径。

    Returns:
        探测结果；ffprobe 不可用或解析失败时各字段为 None。
    """
    try:
        import json
        import subprocess

        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,bit_rate:stream=width,height,codec_type",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if completed.returncode != 0:
            return MediaInfoResult()

        payload = json.loads(completed.stdout or "{}")
        fmt = payload.get("format") or {}
        duration = float(fmt["duration"]) if fmt.get("duration") else None
        bitrate = int(float(fmt["bit_rate"])) if fmt.get("bit_rate") else None

        width: Optional[int] = None
        height: Optional[int] = None
        for stream in payload.get("streams") or []:
            if stream.get("codec_type") == "video":
                width = int(stream["width"]) if stream.get("width") else None
                height = int(stream["height"]) if stream.get("height") else None
                break

        return MediaInfoResult(
            duration=duration, width=width, height=height, bitrate=bitrate
        )
    except FileNotFoundError:
        return MediaInfoResult()
    except Exception as exc:
        logger.debug(f"ffprobe 探测失败 {path}: {exc}")
        return MediaInfoResult()


def _merge(primary: MediaInfoResult, fallback: MediaInfoResult) -> MediaInfoResult:
    """用 fallback 补齐 primary 中缺失（None）的字段。

    Args:
        primary: 优先结果。
        fallback: 用于补齐的结果。

    Returns:
        合并后的结果。
    """
    return MediaInfoResult(
        duration=primary.duration if primary.duration is not None else fallback.duration,
        width=primary.width if primary.width is not None else fallback.width,
        height=primary.height if primary.height is not None else fallback.height,
        bitrate=primary.bitrate if primary.bitrate is not None else fallback.bitrate,
    )


def extract_duration(path: Path) -> Optional[float]:
    """提取媒体文件时长（秒）

    保留的兼容入口，内部复用 extract_media_info。

    Args:
        path: 文件路径

    Returns:
        时长（秒），失败返回 None
    """
    return extract_media_info(path).duration


def is_media_file(path: Path) -> bool:
    """检查文件是否为媒体文件（视频或音频）

    Args:
        path: 文件路径

    Returns:
        是否为媒体文件
    """
    ext = path.suffix.lower().lstrip(".")
    return ext in VIDEO_EXTENSIONS or ext in AUDIO_EXTENSIONS
