"""标签 CRUD 与工作区隔离测试"""

from __future__ import annotations

from app.core.tag_manager import TagSpec
from app.db import Repo


class TestTagWorkspaceIsolation:
    """验证 0.5.0 引入的标签工作区隔离：同名标签可在不同 workspace 共存。"""

    def test_create_same_name_in_different_workspaces(self, repo: Repo):
        repo.create_tag(TagSpec(name="重要"), workspace="D:/work")
        repo.create_tag(TagSpec(name="重要"), workspace="D:/personal")
        repo.session.commit()

        work = repo.get_tag_by_name_and_workspace("重要", workspace="D:/work")
        personal = repo.get_tag_by_name_and_workspace("重要", workspace="D:/personal")

        assert work is not None
        assert personal is not None
        assert work.id != personal.id

    def test_get_or_create_returns_existing(self, repo: Repo):
        t1 = repo.get_or_create_tag(TagSpec(name="风景"), workspace="D:/photos")
        repo.session.commit()
        t2 = repo.get_or_create_tag(TagSpec(name="风景"), workspace="D:/photos")
        repo.session.commit()

        assert t1.id == t2.id

    def test_list_tags_scoped_to_workspace(self, repo: Repo):
        repo.create_tag(TagSpec(name="A"), workspace="D:/ws1")
        repo.create_tag(TagSpec(name="B"), workspace="D:/ws2")
        repo.create_tag(TagSpec(name="Global"))  # workspace=None
        repo.session.commit()

        ws1_tags = repo.list_tags(root="D:/ws1")
        names = {t.name for t in ws1_tags}
        # 当前工作区标签 + 全局标签都应可见
        assert "A" in names
        assert "Global" in names
        assert "B" not in names


class TestTagParentChild:
    def test_create_with_parent_id(self, repo: Repo):
        parent = repo.create_tag(TagSpec(name="动物"))
        repo.session.commit()
        child = repo.create_tag(TagSpec(name="猫"), parent_id=parent.id)
        repo.session.commit()

        assert child.parent_id == parent.id

    def test_delete_tag_removes_associations(self, repo: Repo):
        tag = repo.create_tag(TagSpec(name="标签"))
        repo.session.commit()

        from tests.conftest import make_meta
        f = repo.upsert_file(make_meta("D:/x.jpg"))
        repo.attach_tags(f, [tag])
        repo.session.commit()

        assert len(repo.get_tags_for_file(f.id)) == 1

        repo.delete_tag(tag.id)
        repo.session.commit()

        assert len(repo.get_tags_for_file(f.id)) == 0
