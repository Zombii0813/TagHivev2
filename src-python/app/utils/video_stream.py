"""视频流式转码工具。

使用 PyAV（FFmpeg 的 Python 绑定，wheel 内置 FFmpeg 动态库）在进程内把浏览器
无法原生播放的视频容器（如 MPEG-TS .ts、RealMedia、WMV 等）实时转封装或转码为
fragmented MP4（fMP4）流，供前端 <video> 在线播放。全程不调用外部 ffmpeg 进程，
延续项目"无系统 ffmpeg 依赖"的约束。

策略：
    - 若视频流已是 H.264、音频流已是 AAC：直接流拷贝（remux），几乎零 CPU
      开销（广电来源的 .ts 绝大多数属此类）；
    - 否则：视频转码为 libx264、音频转码为 aac。

输出使用 movflags=frag_keyframe+empty_moov+default_base_moof，无需回退 seek，
适合边生成边推送的流式场景。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator, Optional, Tuple

logger = logging.getLogger(__name__)

# 浏览器 <video> 能直接解码的编码名（转封装即可，无需重编码）
_H264_NAMES = {"h264", "avc1"}
_AAC_NAMES = {"aac"}

# fMP4 流式输出参数：分片 + 空 moov + 默认 base moof，使输出无需可 seek 的目标
_FMP4_OPTIONS = {"movflags": "frag_keyframe+empty_moov+default_base_moof"}

# 每累积到该字节数就向客户端推送一次
_CHUNK_THRESHOLD = 64 * 1024


def probe_codecs(path: Path) -> Tuple[Optional[str], Optional[str]]:
    """探测视频文件首个视频流与音频流的编码名。

    Args:
        path: 视频文件路径。

    Returns:
        (video_codec, audio_codec)，任一不存在或探测失败时对应项为 None。
    """
    try:
        import av
    except ImportError:
        logger.warning("PyAV (av) 未安装，无法探测编码")
        return None, None

    try:
        with av.open(str(path)) as container:
            vcodec = (
                container.streams.video[0].codec_context.name
                if container.streams.video
                else None
            )
            acodec = (
                container.streams.audio[0].codec_context.name
                if container.streams.audio
                else None
            )
            return vcodec, acodec
    except Exception as exc:
        logger.error(f"探测编码失败 {path}: {exc}")
        return None, None


class _ByteSink:
    """可写字节缓冲。PyAV 以此为输出目标，muxer 写入的数据先落入 buffer，
    再由生成器分块取出推送给客户端。实现 write/seek/tell 以满足 PyAV 的鸭子类型。"""

    def __init__(self) -> None:
        self.buffer = bytearray()

    def write(self, data) -> int:
        self.buffer.extend(data)
        return len(data)

    def seek(self, *args, **kwargs) -> int:
        # empty_moov + frag 模式下 muxer 不回退 seek；提供空实现以防万一
        return 0

    def tell(self) -> int:
        return len(self.buffer)

    def flush(self) -> None:
        pass

    def drain(self) -> bytes:
        """取出并清空当前缓冲。"""
        data = bytes(self.buffer)
        self.buffer.clear()
        return data


def stream_fmp4(path: Path) -> Iterator[bytes]:
    """将视频文件进程内转封装/转码为 fragmented MP4，边生成边产出字节块。

    Args:
        path: 源视频文件路径。

    Yields:
        fMP4 字节块（首块含 ftyp/moov，后续为 moof/mdat 分片）。

    Raises:
        RuntimeError: PyAV 未安装或源文件无视频流时抛出，供端点转 500/415。
    """
    try:
        import av
    except ImportError as exc:
        raise RuntimeError("PyAV (av) 未安装，无法转码视频") from exc

    vcodec, acodec = probe_codecs(path)
    if vcodec is None:
        raise RuntimeError(f"源文件无可用视频流: {path}")

    copy_video = vcodec.lower() in _H264_NAMES
    copy_audio = acodec is not None and acodec.lower() in _AAC_NAMES
    logger.info(
        "转码 %s: video=%s(%s) audio=%s(%s)",
        path.name,
        vcodec,
        "copy" if copy_video else "libx264",
        acodec,
        "copy" if copy_audio else ("aac" if acodec else "none"),
    )

    yield from _run_pipeline(av, path, copy_video, copy_audio)


def _run_pipeline(av, path: Path, copy_video: bool, copy_audio: bool) -> Iterator[bytes]:
    """执行 demux→(copy|encode)→mux fMP4 的流水线并分块产出字节。"""
    sink = _ByteSink()
    in_container = None
    out_container = None
    try:
        in_container = av.open(str(path))
        out_container = av.open(sink, mode="w", format="mp4", options=_FMP4_OPTIONS)

        in_video = in_container.streams.video[0]
        in_video.thread_type = "AUTO"
        in_audio = in_container.streams.audio[0] if in_container.streams.audio else None

        # 建立输出流：copy 用模板流，转码则新建编码器
        if copy_video:
            out_video = out_container.add_stream_from_template(in_video)
        else:
            out_video = out_container.add_stream("libx264", rate=in_video.average_rate or 30)
            out_video.width = in_video.codec_context.width
            out_video.height = in_video.codec_context.height
            out_video.pix_fmt = "yuv420p"
            out_video.options = {"preset": "veryfast", "crf": "23"}

        out_audio = None
        audio_bsf = None
        if in_audio is not None:
            if copy_audio:
                out_audio = out_container.add_stream_from_template(in_audio)
                # 关键：TS 中 AAC 为 ADTS 封装，MP4 需裸 AAC(ASC)。命令行 ffmpeg 会
                # 自动插入 aac_adtstoasc，手动 mux 不会，否则 mux 报
                # "Operation not permitted"。此处显式挂接该比特流过滤器。
                audio_bsf = _make_bsf(av, "aac_adtstoasc", in_audio)
            else:
                out_audio = out_container.add_stream("aac")

        # 逐包处理：muxer 写出的字节累积在 sink，达阈值即推送，实现渐进式播放
        demux_streams = [in_video] + ([in_audio] if in_audio else [])
        for packet in in_container.demux(*demux_streams):
            if packet.dts is None:
                continue
            if packet.stream is in_video:
                _handle_stream(packet, out_video, out_container, copy_video, None)
            elif in_audio is not None and packet.stream is in_audio:
                _handle_stream(packet, out_audio, out_container, copy_audio, audio_bsf)
            if sink.tell() >= _CHUNK_THRESHOLD:
                yield sink.drain()

        # 冲刷编码器余下帧
        if not copy_video:
            _flush_encoder(out_video, out_container)
        if out_audio is not None and not copy_audio:
            _flush_encoder(out_audio, out_container)

        out_container.close()
        out_container = None
        tail = sink.drain()
        if tail:
            yield tail
    except GeneratorExit:
        # 客户端断开（切换文件/关闭预览）：静默结束，进入 finally 清理
        logger.debug("转码流被客户端中断: %s", path.name)
        raise
    except Exception as exc:
        logger.error(f"转码流出错 {path}: {exc}")
        raise
    finally:
        if out_container is not None:
            try:
                out_container.close()
            except Exception:
                pass
        if in_container is not None:
            try:
                in_container.close()
            except Exception:
                pass


def _make_bsf(av, name: str, in_stream):
    """创建比特流过滤器上下文；不可用时返回 None（降级为不过滤）。"""
    try:
        return av.BitStreamFilterContext(name, in_stream)
    except Exception as exc:
        logger.warning("比特流过滤器 %s 创建失败，将不过滤: %s", name, exc)
        return None


def _handle_stream(packet, out_stream, out_container, copy: bool, bsf) -> None:
    """处理单个 demux 出的 packet：copy 直接改流后 mux；否则解码→编码→mux。

    Args:
        bsf: 可选比特流过滤器（如 AAC copy 的 aac_adtstoasc）；None 表示不过滤。

    注：muxer 写出的字节落入 sink 缓冲，由上层 drain 后推送，本函数不直接产出字节。
    """
    if copy:
        # 流拷贝：先经比特流过滤（若有），再把 packet 归属到输出流后 mux
        packets = bsf.filter(packet) if bsf is not None else [packet]
        for p in packets:
            p.stream = out_stream
            out_container.mux(p)
        return

    # 转码路径：解码原始帧后交给输出编码器
    for frame in packet.decode():
        for out_packet in out_stream.encode(frame):
            out_container.mux(out_packet)


def _flush_encoder(out_stream, out_container) -> None:
    """冲刷编码器中缓冲的剩余帧。"""
    for out_packet in out_stream.encode(None):
        out_container.mux(out_packet)
