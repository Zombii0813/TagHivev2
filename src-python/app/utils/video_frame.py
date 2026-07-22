"""视频首帧提取工具

使用 PyAV（FFmpeg 的 Python 绑定，wheel 内置 FFmpeg 动态库）在进程内解码视频
首帧，无需依赖系统安装的 ffmpeg 命令行工具，从而支持在未安装 ffmpeg 的平台上生成
视频缩略图。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


def extract_video_frame(
    path: Path,
    seek_seconds: float = 1.0,
) -> Optional[Image.Image]:
    """解码视频指定时间点附近的一帧并返回 PIL 图像。

    优先 seek 到 ``seek_seconds`` 附近取帧（跳过纯黑的片头）；若视频过短或 seek
    失败，则回退到从头解码第一帧。整个过程在进程内完成，不调用外部 ffmpeg 进程。

    Args:
        path: 视频文件路径。
        seek_seconds: 期望抽取的时间点（秒），默认第 1 秒。

    Returns:
        解码得到的 PIL 图像（RGB）；无法解码时返回 None。
    """
    try:
        import av
    except ImportError:
        logger.warning("PyAV (av) 未安装，无法生成视频缩略图")
        return None

    try:
        with av.open(str(path)) as container:
            if not container.streams.video:
                return None

            stream = container.streams.video[0]
            # 允许多线程解码，加快取帧速度
            stream.thread_type = "AUTO"

            # 尝试 seek 到目标时间点附近的关键帧
            if seek_seconds > 0 and stream.time_base:
                try:
                    target_ts = int(seek_seconds / stream.time_base)
                    container.seek(target_ts, stream=stream, any_frame=False)
                except Exception as exc:
                    logger.debug(f"seek 失败，改从头解码 {path}: {exc}")

            frame = _first_decodable_frame(container, stream)

            # seek 后未取到帧（如视频短于 seek_seconds）：重新打开从头解码
            if frame is None:
                return _decode_from_start(path)

            return frame.to_image()

    except Exception as exc:
        logger.error(f"PyAV 解码视频帧失败 {path}: {exc}")
        return None


def _first_decodable_frame(container, stream):
    """从容器当前位置解码并返回第一帧，失败返回 None。"""
    try:
        for frame in container.decode(stream):
            return frame
    except Exception as exc:
        logger.debug(f"解码帧失败: {exc}")
    return None


def _decode_from_start(path: Path):
    """回退方案：重新打开视频，从头解码第一帧并返回 PIL 图像。"""
    try:
        import av

        with av.open(str(path)) as container:
            if not container.streams.video:
                return None
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            frame = _first_decodable_frame(container, stream)
            if frame is not None:
                return frame.to_image()
    except Exception as exc:
        logger.error(f"PyAV 从头解码失败 {path}: {exc}")
    return None
