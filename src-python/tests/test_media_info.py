"""媒体元数据探测与惰性缓存测试

覆盖：
1. extract_media_info 对非媒体文件的短路返回
2. PyAV 未取到字段时 pymediainfo 兜底补齐、比特率按文件大小估算
3. Repo.update_media_info 回写与 media_probed 标记
"""

from __future__ import annotations

from pathlib import Path

from app.db import Repo
from app.utils import media_info as media_info_module
from app.utils.media_info import MediaInfoResult, extract_media_info, is_media_file

from tests.conftest import make_meta


class TestExtractMediaInfo:
    """媒体信息探测"""

    def test_non_media_file_returns_empty(self, tmp_path: Path):
        """非媒体扩展名直接返回空结果，不触发任何探测。"""
        target = tmp_path / "note.txt"
        target.write_text("hello", encoding="utf-8")

        result = extract_media_info(target)

        assert result.is_empty
        assert not is_media_file(target)

    def test_mediainfo_fills_missing_fields(self, tmp_path: Path, monkeypatch):
        """PyAV 只拿到时长时，分辨率由 pymediainfo 补齐。"""
        target = tmp_path / "clip.mp4"
        target.write_bytes(b"\x00" * 2048)

        monkeypatch.setattr(
            media_info_module,
            "_probe_with_pyav",
            lambda _path: MediaInfoResult(duration=10.0, bitrate=800_000),
        )
        monkeypatch.setattr(
            media_info_module,
            "_probe_with_mediainfo",
            lambda _path: MediaInfoResult(duration=99.0, width=1920, height=1080),
        )

        result = extract_media_info(target)

        # PyAV 已有的字段优先，不被兜底覆盖
        assert result.duration == 10.0
        assert result.bitrate == 800_000
        # 缺失字段由兜底补齐
        assert result.width == 1920
        assert result.height == 1080

    def test_bitrate_estimated_from_size(self, tmp_path: Path, monkeypatch):
        """容器未声明比特率时，按「文件大小 × 8 / 时长」估算。"""
        target = tmp_path / "clip.ts"
        target.write_bytes(b"\x00" * 1000)

        monkeypatch.setattr(
            media_info_module,
            "_probe_with_pyav",
            lambda _path: MediaInfoResult(duration=2.0, width=640, height=360),
        )

        result = extract_media_info(target)

        assert result.bitrate == 4000  # 1000 字节 * 8 / 2 秒

    def test_all_probes_failing_returns_empty(self, tmp_path: Path, monkeypatch):
        """所有探测手段都失败时返回空结果，而非抛异常。"""
        target = tmp_path / "broken.mkv"
        target.write_bytes(b"not a real video")

        monkeypatch.setattr(
            media_info_module, "_probe_with_pyav", lambda _path: MediaInfoResult()
        )
        monkeypatch.setattr(
            media_info_module, "_probe_with_mediainfo", lambda _path: MediaInfoResult()
        )

        assert extract_media_info(target).is_empty


class TestUpdateMediaInfo:
    """媒体元数据落库"""

    def test_update_writes_fields_and_marks_probed(self, repo: Repo):
        """回写后各字段可读，且 media_probed 置 1。"""
        files = repo.bulk_upsert_files([make_meta("D:/videos/a.mp4", type_="video")])
        repo.session.commit()
        file_id = int(files[0].id)

        repo.update_media_info(
            file_id, duration=125.5, width=1920, height=1080, bitrate=5_000_000
        )
        repo.session.commit()

        row = repo.get_file_by_id(file_id)
        assert row is not None
        assert row.duration == 125.5
        assert row.width == 1920
        assert row.height == 1080
        assert row.bitrate == 5_000_000
        assert row.media_probed == 1

    def test_rescan_keeps_probed_values(self, repo: Repo):
        """文件未变化时重扫不得清空已探测的时长/分辨率/比特率。

        扫描侧不做媒体探测（FileMeta.duration 恒为 None），若直接覆盖会把
        惰性探测结果清空，导致详情栏永久显示 '-' 且不再重探。
        """
        meta = make_meta("D:/videos/keep.mp4", type_="video")
        files = repo.bulk_upsert_files([meta])
        repo.session.commit()
        file_id = int(files[0].id)

        repo.update_media_info(
            file_id, duration=88.0, width=1280, height=720, bitrate=2_000_000
        )
        repo.session.commit()

        # 同一文件重扫（size/modified_at 均未变）
        repo.bulk_upsert_files_fast([meta], {meta.path.as_posix(): file_id})
        repo.session.commit()

        row = repo.get_file_by_id(file_id)
        assert row is not None
        assert row.duration == 88.0
        assert row.width == 1280
        assert row.height == 720
        assert row.bitrate == 2_000_000
        assert row.media_probed == 1

    def test_rescan_resets_cache_when_file_changed(self, repo: Repo):
        """文件大小变化时清除探测缓存，使详情栏重新探测。"""
        meta = make_meta("D:/videos/edited.mp4", type_="video", size=1024)
        files = repo.bulk_upsert_files([meta])
        repo.session.commit()
        file_id = int(files[0].id)

        repo.update_media_info(
            file_id, duration=88.0, width=1280, height=720, bitrate=2_000_000
        )
        repo.session.commit()

        # 文件被替换：大小变化
        changed = make_meta("D:/videos/edited.mp4", type_="video", size=999_999)
        repo.bulk_upsert_files_fast([changed], {changed.path.as_posix(): file_id})
        repo.session.commit()

        row = repo.get_file_by_id(file_id)
        assert row is not None
        assert row.width is None
        assert row.height is None
        assert row.bitrate is None
        assert not row.media_probed

    def test_failed_probe_still_marks_probed(self, repo: Repo):
        """探测失败（全 None）也要打标记，避免每次打开详情栏都重试。"""
        files = repo.bulk_upsert_files([make_meta("D:/videos/broken.rmvb", type_="video")])
        repo.session.commit()
        file_id = int(files[0].id)

        repo.update_media_info(
            file_id, duration=None, width=None, height=None, bitrate=None
        )
        repo.session.commit()

        row = repo.get_file_by_id(file_id)
        assert row is not None
        assert row.duration is None
        assert row.media_probed == 1
