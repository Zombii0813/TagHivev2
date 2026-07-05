"""explorer 浏览模式子目录派生测试

验证 _build_child_dirs：
- 直接子目录来自文件系统扫描（含空目录），按资源管理器规则排序
- file_count 为直接子文件数
- cover_file_ids 取子目录内（含深层）前若干个 image/video 文件
"""

from __future__ import annotations

from pathlib import Path

from app.api.routes import _build_child_dirs, _COVER_LIMIT
from app.db import Repo
from tests.conftest import make_meta


def _seed(root: Path, repo: Repo) -> None:
    """在磁盘建目录结构，并把媒体文件写入 DB。

    结构：
        root/
          a/           (2 张图 + 1 个深层视频)
            1.jpg, 2.jpg
            sub/3.mp4
          b/           (空目录，无文件)
          c/           (仅 1 个非媒体 txt)
            note.txt
    """
    for d in ["a", "a/sub", "b", "c"]:
        (root / d).mkdir(parents=True, exist_ok=True)

    rp = root.as_posix()
    repo.upsert_file(make_meta(f"{rp}/a/1.jpg", type_="image"))
    repo.upsert_file(make_meta(f"{rp}/a/2.jpg", type_="image"))
    repo.upsert_file(make_meta(f"{rp}/a/sub/3.mp4", type_="video"))
    repo.upsert_file(make_meta(f"{rp}/c/note.txt", type_="document"))


def test_child_dirs_listed_with_empty_dir(repo: Repo, tmp_path: Path):
    """三个子目录均返回，含空目录 b"""
    root = tmp_path / "ws"
    root.mkdir()
    _seed(root, repo)

    dirs = _build_child_dirs(root, root.as_posix(), repo)
    names = [d.name for d in dirs]
    assert names == ["a", "b", "c"]


def test_child_dir_file_count_is_direct(repo: Repo, tmp_path: Path):
    """file_count 只统计直接子文件，不含深层"""
    root = tmp_path / "ws"
    root.mkdir()
    _seed(root, repo)

    by_name = {d.name: d for d in _build_child_dirs(root, root.as_posix(), repo)}
    assert by_name["a"].file_count == 2  # 1.jpg, 2.jpg（不含 sub/3.mp4）
    assert by_name["b"].file_count == 0
    assert by_name["c"].file_count == 1  # note.txt


def test_child_dir_cover_includes_deep_media(repo: Repo, tmp_path: Path):
    """封面取深层媒体文件，非媒体与空目录封面为空"""
    root = tmp_path / "ws"
    root.mkdir()
    _seed(root, repo)

    by_name = {d.name: d for d in _build_child_dirs(root, root.as_posix(), repo)}
    # a 目录：2 张图 + 深层 1 个视频 = 3 个封面候选（不超过上限）
    assert len(by_name["a"].cover_file_ids) == 3
    assert len(by_name["a"].cover_file_ids) <= _COVER_LIMIT
    # b 空目录、c 仅有非媒体文件 → 无封面
    assert by_name["b"].cover_file_ids == []
    assert by_name["c"].cover_file_ids == []


def test_child_dir_cover_capped(repo: Repo, tmp_path: Path):
    """封面数量不超过 _COVER_LIMIT"""
    root = tmp_path / "ws"
    root.mkdir()
    (root / "many").mkdir()
    rp = root.as_posix()
    for i in range(_COVER_LIMIT + 5):
        repo.upsert_file(make_meta(f"{rp}/many/{i}.jpg", type_="image"))

    by_name = {d.name: d for d in _build_child_dirs(root, rp, repo)}
    assert len(by_name["many"].cover_file_ids) == _COVER_LIMIT


def test_child_dir_custom_cover_returned(repo: Repo, tmp_path: Path):
    """设置自定义封面后，_build_child_dirs 在 cover_path 中返回该路径"""
    root = tmp_path / "ws"
    root.mkdir()
    _seed(root, repo)
    rp = root.as_posix()

    # 未设置时 cover_path 为 None
    before = {d.name: d for d in _build_child_dirs(root, rp, repo)}
    assert before["a"].cover_path is None

    # 设置 a 目录自定义封面
    repo.set_folder_cover(f"{rp}/a", f"{rp}/a/1.jpg", rp)
    after = {d.name: d for d in _build_child_dirs(root, rp, repo)}
    assert after["a"].cover_path == f"{rp}/a/1.jpg"
    # 九宫格候选仍返回，前端优先用自定义封面
    assert len(after["a"].cover_file_ids) > 0
    # 其他目录不受影响
    assert after["b"].cover_path is None

    # 清除后恢复 None
    repo.clear_folder_cover(f"{rp}/a")
    cleared = {d.name: d for d in _build_child_dirs(root, rp, repo)}
    assert cleared["a"].cover_path is None
