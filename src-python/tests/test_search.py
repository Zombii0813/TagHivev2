"""搜索功能与 SQL 分页测试"""

from __future__ import annotations

from app.core.search import SearchQuery
from app.db import Repo

from tests.conftest import make_meta


class TestSearchBasics:
    def test_search_by_text_finds_match(self, repo: Repo):
        repo.upsert_file(make_meta("D:/a/holiday-photo.jpg"))
        repo.upsert_file(make_meta("D:/a/document.pdf", type_="doc"))
        repo.session.commit()

        results = repo.search(SearchQuery(text="holiday"))
        assert len(results) == 1
        assert results[0].name == "holiday-photo.jpg"

    def test_search_by_type_filter(self, repo: Repo):
        repo.upsert_file(make_meta("D:/a.jpg", type_="image"))
        repo.upsert_file(make_meta("D:/b.mp4", type_="video"))
        repo.upsert_file(make_meta("D:/c.jpg", type_="image"))
        repo.session.commit()

        results = repo.search(SearchQuery(types=("image",)))
        names = sorted(r.name for r in results)
        assert names == ["a.jpg", "c.jpg"]

    def test_search_by_root_prefix(self, repo: Repo):
        repo.upsert_file(make_meta("D:/photos/a.jpg"))
        repo.upsert_file(make_meta("D:/videos/b.mp4", type_="video"))
        repo.session.commit()

        results = repo.search(SearchQuery(root="D:/photos"))
        assert len(results) == 1
        assert results[0].name == "a.jpg"


class TestPagination:
    """验证 P0-1：count + LIMIT/OFFSET 各自走纯 SQL，不再"全量加载再切片"。"""

    def test_count_search_returns_exact_total(self, repo: Repo):
        metas = [make_meta(f"D:/f{i}.jpg") for i in range(25)]
        repo.bulk_upsert_files(metas)

        total = repo.count_search(SearchQuery())
        assert total == 25

    def test_search_with_offset_returns_page(self, repo: Repo):
        # 按 name 升序时 f00.jpg ~ f09.jpg 落在第一页
        metas = [make_meta(f"D:/f{i:02d}.jpg") for i in range(25)]
        repo.bulk_upsert_files(metas)

        page = repo.search_with_offset(SearchQuery(sort_by="name"), offset=0, limit=10)
        assert len(page.items) == 10
        assert page.items[0].name == "f00.jpg"
        assert page.items[-1].name == "f09.jpg"

        page2 = repo.search_with_offset(SearchQuery(sort_by="name"), offset=10, limit=10)
        assert len(page2.items) == 10
        assert page2.items[0].name == "f10.jpg"

    def test_count_with_filter_matches_search(self, repo: Repo):
        for i in range(10):
            repo.upsert_file(make_meta(f"D:/img{i}.jpg", type_="image"))
        for i in range(5):
            repo.upsert_file(make_meta(f"D:/vid{i}.mp4", type_="video"))
        repo.session.commit()

        q = SearchQuery(types=("image",))
        assert repo.count_search(q) == 10
        page = repo.search_with_offset(q, offset=0, limit=100)
        assert len(page.items) == 10
