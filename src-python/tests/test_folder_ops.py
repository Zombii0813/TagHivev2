"""文件夹移动/复制 API 测试

覆盖：
- 文件夹移动：子文件记录路径前缀更新、文件 id 与标签保留、跨工作区标签清理
- 文件夹复制：副本作为全新记录入库且不含标签
- 防自包含：把文件夹移动/复制到自身或子目录时报错
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.db import Repo
from app.db.models import Tag
from app.api.routes import move_folder, copy_folder
from app.api.models import FolderMoveRequestDTO, FolderCopyRequestDTO


def _make_file(root: Path, rel: str, content: bytes = b"x") -> Path:
    """在磁盘上创建真实文件（含父目录），返回其路径。"""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def _index(repo: Repo, path: Path):
    """把磁盘文件登记入库，返回 File 记录。"""
    from app.core.indexer import build_file_meta
    return repo.upsert_file(build_file_meta(path))


class TestFolderMove:
    @pytest.mark.asyncio
    async def test_move_updates_child_paths_and_keeps_id_and_tags(self, repo: Repo, tmp_path: Path):
        """移动文件夹后，子文件记录路径更新，文件 id 与标签保留。"""
        ws_a = tmp_path / "wsA"
        ws_b = tmp_path / "wsB"
        ws_b.mkdir()
        src = ws_a / "album"
        f1 = _make_file(ws_a, "album/a.jpg")
        f2 = _make_file(ws_a, "album/sub/b.jpg")

        row1 = _index(repo, f1)
        row2 = _index(repo, f2)
        id1, id2 = row1.id, row2.id
        # 给 f1 打一个全局标签（workspace=None），移动后应保留
        tag = Tag(name="keep", workspace=None)
        repo.session.add(tag)
        repo.session.flush()
        row1.tags = [tag]
        repo.session.commit()

        await move_folder(
            FolderMoveRequestDTO(source_path=str(src), target_dir=str(ws_b)),
            repo=repo,
        )

        # 物理移动完成
        assert not src.exists()
        assert (ws_b / "album" / "a.jpg").exists()
        assert (ws_b / "album" / "sub" / "b.jpg").exists()

        # id 保留、路径更新
        moved1 = repo.get_file_by_id(id1)
        moved2 = repo.get_file_by_id(id2)
        assert moved1 is not None and moved2 is not None
        assert moved1.path == (ws_b / "album" / "a.jpg").as_posix()
        assert moved2.path == (ws_b / "album" / "sub" / "b.jpg").as_posix()
        # 全局标签保留
        assert [t.name for t in moved1.tags] == ["keep"]

    @pytest.mark.asyncio
    async def test_cross_workspace_strips_foreign_tags(self, repo: Repo, tmp_path: Path):
        """跨工作区移动时，剥离不属于目标工作区的标签。"""
        ws_a = tmp_path / "wsA"
        ws_b = tmp_path / "wsB"
        ws_b.mkdir()
        src = ws_a / "album"
        f1 = _make_file(ws_a, "album/a.jpg")
        row1 = _index(repo, f1)
        fid = row1.id

        # 属于 wsA 的标签（移动到 wsB 后应被剥离）
        tag_a = Tag(name="only-a", workspace=ws_a.as_posix())
        # 全局标签（应保留）
        tag_global = Tag(name="global", workspace=None)
        repo.session.add_all([tag_a, tag_global])
        repo.session.flush()
        row1.tags = [tag_a, tag_global]
        repo.session.commit()

        await move_folder(
            FolderMoveRequestDTO(
                source_path=str(src),
                target_dir=str(ws_b),
                target_workspace=ws_b.as_posix(),
            ),
            repo=repo,
        )

        moved = repo.get_file_by_id(fid)
        assert moved is not None
        names = sorted(t.name for t in moved.tags)
        assert names == ["global"]

    @pytest.mark.asyncio
    async def test_move_into_self_raises(self, repo: Repo, tmp_path: Path):
        """把文件夹移动到自身/子目录时报错。"""
        ws = tmp_path / "ws"
        src = ws / "album"
        src.mkdir(parents=True)
        (src / "sub").mkdir()

        with pytest.raises(HTTPException) as exc:
            await move_folder(
                FolderMoveRequestDTO(source_path=str(src), target_dir=str(src / "sub")),
                repo=repo,
            )
        assert exc.value.status_code == 400


class TestFolderCopy:
    @pytest.mark.asyncio
    async def test_copy_creates_new_records_without_tags(self, repo: Repo, tmp_path: Path):
        """复制文件夹：副本作为全新记录入库，不含标签，原记录保留。"""
        ws_a = tmp_path / "wsA"
        ws_b = tmp_path / "wsB"
        ws_b.mkdir()
        src = ws_a / "album"
        f1 = _make_file(ws_a, "album/a.jpg")
        row1 = _index(repo, f1)
        tag = Tag(name="t", workspace=None)
        repo.session.add(tag)
        repo.session.flush()
        row1.tags = [tag]
        repo.session.commit()
        original_id = row1.id

        result = await copy_folder(
            FolderCopyRequestDTO(source_path=str(src), target_dir=str(ws_b)),
            repo=repo,
        )

        # 物理副本存在，原目录仍在
        assert src.exists()
        assert (ws_b / "album" / "a.jpg").exists()

        # 副本是新记录、无标签
        assert len(result.files) == 1
        copy_summary = result.files[0]
        assert copy_summary.id != original_id
        assert copy_summary.tag_ids == []
        # 原记录与标签未受影响
        original = repo.get_file_by_id(original_id)
        assert original is not None
        assert [t.name for t in original.tags] == ["t"]

    @pytest.mark.asyncio
    async def test_copy_into_self_raises(self, repo: Repo, tmp_path: Path):
        ws = tmp_path / "ws"
        src = ws / "album"
        src.mkdir(parents=True)

        with pytest.raises(HTTPException) as exc:
            await copy_folder(
                FolderCopyRequestDTO(source_path=str(src), target_dir=str(src)),
                repo=repo,
            )
        assert exc.value.status_code == 400
