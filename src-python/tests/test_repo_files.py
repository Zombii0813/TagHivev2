"""Repo 基础 CRUD 与 parent_dir 物化列测试"""

from __future__ import annotations

from app.db import Repo
from app.db.models import File
from sqlalchemy import select

from tests.conftest import make_meta


class TestFileCRUD:
    def test_upsert_inserts_new_file(self, repo: Repo):
        meta = make_meta("D:/photos/2026/a.jpg")
        file_row = repo.upsert_file(meta)
        repo.session.commit()

        assert file_row.id is not None
        assert file_row.path == "D:/photos/2026/a.jpg"
        assert file_row.name == "a.jpg"
        assert file_row.ext == "jpg"
        assert file_row.type == "image"

    def test_upsert_updates_on_path_conflict(self, repo: Repo):
        repo.upsert_file(make_meta("D:/a.jpg", size=100))
        repo.session.commit()

        repo.upsert_file(make_meta("D:/a.jpg", size=999))
        repo.session.commit()

        files = repo.list_files()
        assert len(files) == 1
        assert files[0].size == 999

    def test_bulk_upsert_processes_batch(self, repo: Repo):
        metas = [make_meta(f"D:/dir/f{i}.jpg") for i in range(50)]
        repo.bulk_upsert_files(metas)

        files = repo.list_files()
        assert len(files) == 50

    def test_get_by_path_normalizes_separators(self, repo: Repo):
        repo.upsert_file(make_meta("D:/a/b/c.jpg"))
        repo.session.commit()

        # Windows 风格反斜杠也能找到（Repo 内部 as_posix）
        found = repo.get_file_by_path("D:\\a\\b\\c.jpg")
        assert found is not None
        assert found.name == "c.jpg"

    def test_delete_files_removes_records(self, repo: Repo):
        f = repo.upsert_file(make_meta("D:/x.jpg"))
        repo.session.commit()
        fid = f.id

        repo.delete_files([fid])
        repo.session.commit()

        assert repo.get_file_by_id(fid) is None


class TestParentDirColumn:
    """验证 P0-2 引入的 parent_dir 物化列在各种写入路径上都被正确填充。"""

    def test_upsert_fills_parent_dir(self, repo: Repo):
        repo.upsert_file(make_meta("D:/photos/2026/a.jpg"))
        repo.session.commit()

        row = repo.get_file_by_path("D:/photos/2026/a.jpg")
        assert row.parent_dir == "D:/photos/2026"

    def test_bulk_upsert_fills_parent_dir(self, repo: Repo):
        metas = [
            make_meta("D:/photos/2026/a.jpg"),
            make_meta("D:/photos/2026/b.jpg"),
            make_meta("D:/videos/c.mp4", type_="video"),
        ]
        repo.bulk_upsert_files(metas)

        rows = repo.list_files()
        parent_dirs = {r.path: r.parent_dir for r in rows}
        assert parent_dirs["D:/photos/2026/a.jpg"] == "D:/photos/2026"
        assert parent_dirs["D:/photos/2026/b.jpg"] == "D:/photos/2026"
        assert parent_dirs["D:/videos/c.mp4"] == "D:/videos"

    def test_root_level_file_has_empty_parent_dir(self, repo: Repo):
        """形如 'a.jpg' 这种没有目录分隔符的路径，parent_dir 应为空字符串而非 None。"""
        repo.upsert_file(make_meta("a.jpg"))
        repo.session.commit()

        row = repo.get_file_by_path("a.jpg")
        assert row.parent_dir == ""

    def test_parent_dir_query_returns_only_direct_children(self, repo: Repo):
        """模拟 routes.get_folder_contents 的核心查询：parent_dir = ? 只取直接子文件。"""
        metas = [
            make_meta("D:/photos/2026/a.jpg"),        # 直接子文件
            make_meta("D:/photos/2026/b.jpg"),        # 直接子文件
            make_meta("D:/photos/2026/06/deep.jpg"),  # 深层文件，不应命中
            make_meta("D:/other/c.jpg"),              # 其他目录
        ]
        repo.bulk_upsert_files(metas)

        stmt = select(File).where(File.parent_dir == "D:/photos/2026")
        results = list(repo.session.execute(stmt).scalars())
        names = sorted(r.name for r in results)
        assert names == ["a.jpg", "b.jpg"]
