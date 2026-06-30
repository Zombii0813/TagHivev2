"""扫描服务的数据保护测试

重点验证：当工作区根目录不可达（如外部移动硬盘已拔出）时，
扫描不会把数据库中该工作区的文件记录误判为「已删除」而清空。
"""

from __future__ import annotations

from pathlib import Path

from app.db import Repo
from app.services.scan_service import ScanService

from tests.conftest import make_meta


class TestScanDataProtection:
    """根目录不可达时的数据保护"""

    def test_scan_aborts_when_root_unavailable(self, repo: Repo, tmp_path: Path):
        """根目录不存在时，扫描立即返回 0 且不删除任何已有记录。"""
        # 预置：模拟某工作区下已有文件记录（如移动硬盘 X:/photos）
        repo.bulk_upsert_files([
            make_meta("X:/photos/a.jpg"),
            make_meta("X:/photos/b.jpg"),
            make_meta("X:/photos/sub/c.jpg"),
        ])
        repo.session.commit()
        assert len(repo.list_files()) == 3

        # 模拟移动硬盘拔出：根目录不可达
        missing_root = tmp_path / "removable_drive_gone"
        assert not missing_root.exists()

        service = ScanService(repo.session)
        count = service.scan_workspace(missing_root)

        # 扫描应中止，返回 0
        assert count == 0
        # 关键断言：原有记录必须完整保留，绝不能被清理
        assert len(repo.list_files()) == 3

    def test_cleanup_skips_when_root_unavailable(self, repo: Repo, tmp_path: Path):
        """即使直接调用清理函数，根目录不可达时也不应删除记录。"""
        repo.bulk_upsert_files([
            make_meta("X:/photos/a.jpg"),
            make_meta("X:/photos/b.jpg"),
        ])
        repo.session.commit()

        missing_root = tmp_path / "gone"
        service = ScanService(repo.session)
        # paths_seen 为空模拟「一个文件都没扫到」的极端场景
        service._cleanup_stale_files(repo, missing_root.resolve(), set())

        assert len(repo.list_files()) == 2

    def test_cleanup_removes_stale_when_root_available(self, repo: Repo, tmp_path: Path):
        """根目录可访问时，清理逻辑应正常删除已不存在的文件记录。"""
        root = tmp_path / "ws"
        root.mkdir()
        root_posix = root.as_posix()

        repo.bulk_upsert_files([
            make_meta(f"{root_posix}/keep.jpg"),
            make_meta(f"{root_posix}/stale.jpg"),
        ])
        repo.session.commit()

        service = ScanService(repo.session)
        # 仅 keep.jpg 被扫描到，stale.jpg 应被清理
        service._cleanup_stale_files(repo, root.resolve(), {f"{root_posix}/keep.jpg"})
        repo.session.commit()

        remaining = [f.path for f in repo.list_files()]
        assert f"{root_posix}/keep.jpg" in remaining
        assert f"{root_posix}/stale.jpg" not in remaining
