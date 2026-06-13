"""标签导入导出 (tag_transfer) 单元测试"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db.models import File as FileModel, FileTag, Tag
from app.db.repo import Repo
from app.services.tag_transfer import (
    EXPORT_SCHEMA_VERSION,
    MAGIC_HEADER,
    ImportPlan,
    ThpackFormatError,
    commit_import,
    export_workspace,
    match_files,
    parse_thpack,
)


WORKSPACE = "E:/ws"


# ---------- 测试辅助 ----------


def _add_file(repo: Repo, path: str, *, size: int = 100, mtime: float = 1700000000.0) -> FileModel:
    posix = Path(path).as_posix()
    name = posix.rsplit("/", 1)[-1]
    parent_dir = posix.rsplit("/", 1)[0] if "/" in posix else ""
    f = FileModel(
        path=posix,
        parent_dir=parent_dir,
        name=name,
        ext="",
        size=size,
        type="document",
        modified_at=mtime,
    )
    repo.session.add(f)
    repo.session.flush()
    return f


def _add_tag(repo: Repo, name: str, *, workspace: str = WORKSPACE, parent_id: int | None = None) -> Tag:
    t = Tag(name=name, workspace=Path(workspace).as_posix(), parent_id=parent_id)
    repo.session.add(t)
    repo.session.flush()
    return t


def _link(repo: Repo, f: FileModel, t: Tag) -> None:
    repo.session.add(FileTag(file_id=f.id, tag_id=t.id))
    repo.session.flush()


# ---------- 序列化往返 ----------


def test_export_then_parse_roundtrip(repo: Repo):
    parent = _add_tag(repo, "项目")
    child = _add_tag(repo, "重要", parent_id=parent.id)
    f = _add_file(repo, f"{WORKSPACE}/docs/readme.md", size=2048, mtime=1733000000.0)
    _link(repo, f, child)

    raw = export_workspace(repo, WORKSPACE)
    assert raw[:4] == MAGIC_HEADER
    assert raw[4] == EXPORT_SCHEMA_VERSION

    payload = parse_thpack(raw)
    assert payload.schema_version == EXPORT_SCHEMA_VERSION
    assert payload.source_workspace == WORKSPACE
    assert {t.name for t in payload.tags} == {"项目", "重要"}

    # 父子关系应保留
    parent_export_id = next(t.export_id for t in payload.tags if t.name == "项目")
    child_meta = next(t for t in payload.tags if t.name == "重要")
    assert child_meta.parent_export_id == parent_export_id

    # 文件标记关联应保留
    assert len(payload.files) == 1
    ef = payload.files[0]
    assert ef.rel_path == "docs/readme.md"
    assert ef.size == 2048
    assert ef.mtime == 1733000000.0
    assert child_meta.export_id in ef.tag_export_ids


def test_export_only_selected_tags(repo: Repo):
    keep = _add_tag(repo, "A")
    drop = _add_tag(repo, "B")
    raw = export_workspace(repo, WORKSPACE, tag_ids=[keep.id])
    payload = parse_thpack(raw)
    assert {t.name for t in payload.tags} == {"A"}


# ---------- magic / version 校验 ----------


def test_parse_rejects_bad_magic():
    with pytest.raises(ThpackFormatError):
        parse_thpack(b"XXXX\x01garbage")


def test_parse_rejects_unknown_version():
    bad = MAGIC_HEADER + bytes([99]) + b"garbage"
    with pytest.raises(ThpackFormatError):
        parse_thpack(bad)


def test_parse_rejects_short():
    with pytest.raises(ThpackFormatError):
        parse_thpack(b"abc")


def test_parse_rejects_corrupt_gzip():
    bad = MAGIC_HEADER + bytes([EXPORT_SCHEMA_VERSION]) + b"not-gzip"
    with pytest.raises(ThpackFormatError):
        parse_thpack(bad)


# ---------- 匹配引擎：三类输出 ----------


def test_match_files_unique_multiple_unmatched(repo: Repo):
    tag = _add_tag(repo, "T")
    # 源 workspace 中的标记文件
    f1 = _add_file(repo, f"{WORKSPACE}/a.txt", size=100, mtime=1000.0)
    f2 = _add_file(repo, f"{WORKSPACE}/b.txt", size=200, mtime=2000.0)
    f3 = _add_file(repo, f"{WORKSPACE}/missing.txt", size=300, mtime=3000.0)
    _link(repo, f1, tag)
    _link(repo, f2, tag)
    _link(repo, f3, tag)
    raw = export_workspace(repo, WORKSPACE)

    # 现在改造 DB 模拟「目标 workspace」：
    # - a.txt 有唯一匹配
    # - b.txt 有两个同名同 size 同 mtime 候选 → 多匹配
    # - missing.txt 被删除 → 未匹配
    repo.session.query(FileTag).delete()
    repo.session.query(FileModel).delete()
    repo.session.flush()
    _add_file(repo, f"{WORKSPACE}/a.txt", size=100, mtime=1000.0)
    _add_file(repo, f"{WORKSPACE}/sub1/b.txt", size=200, mtime=2000.0)
    _add_file(repo, f"{WORKSPACE}/sub2/b.txt", size=200, mtime=2000.0)

    payload = parse_thpack(raw)
    result = match_files(repo, payload, WORKSPACE)

    unique_paths = {e.exported.rel_path for e in result.unique}
    multi_paths = {e.exported.rel_path for e in result.multiple}
    miss_paths = {e.exported.rel_path for e in result.unmatched}

    assert unique_paths == {"a.txt"}
    assert multi_paths == {"b.txt"}
    assert miss_paths == {"missing.txt"}
    multi_entry = result.multiple[0]
    assert len(multi_entry.candidates) == 2


def test_match_files_mtime_tolerance(repo: Repo):
    """mtime 相差 ≤2 秒应命中"""
    tag = _add_tag(repo, "T")
    f = _add_file(repo, f"{WORKSPACE}/a.txt", size=10, mtime=1000.0)
    _link(repo, f, tag)
    raw = export_workspace(repo, WORKSPACE)

    # 模拟目标 DB 中文件 mtime 偏移 1.5 秒（仍在 ±2s 容差内）
    repo.session.query(FileTag).delete()
    repo.session.query(FileModel).delete()
    repo.session.flush()
    _add_file(repo, f"{WORKSPACE}/a.txt", size=10, mtime=1001.5)

    payload = parse_thpack(raw)
    result = match_files(repo, payload, WORKSPACE)
    assert len(result.unique) == 1
    assert not result.unmatched


def test_match_files_mtime_out_of_tolerance(repo: Repo):
    """mtime 相差 >2 秒视为未命中"""
    tag = _add_tag(repo, "T")
    f = _add_file(repo, f"{WORKSPACE}/a.txt", size=10, mtime=1000.0)
    _link(repo, f, tag)
    raw = export_workspace(repo, WORKSPACE)

    repo.session.query(FileTag).delete()
    repo.session.query(FileModel).delete()
    repo.session.flush()
    _add_file(repo, f"{WORKSPACE}/a.txt", size=10, mtime=2000.0)

    payload = parse_thpack(raw)
    result = match_files(repo, payload, WORKSPACE)
    assert len(result.unmatched) == 1
    assert not result.unique


# ---------- commit_import ----------


def test_commit_import_creates_tags_and_links(repo: Repo):
    # 源数据导出
    parent = _add_tag(repo, "项目")
    child = _add_tag(repo, "重要", parent_id=parent.id)
    f = _add_file(repo, f"{WORKSPACE}/a.txt", size=10, mtime=1000.0)
    _link(repo, f, child)
    raw = export_workspace(repo, WORKSPACE)
    payload = parse_thpack(raw)

    # 切换到「目标 workspace」：清空标签和关联，仅保留同名文件
    repo.session.query(FileTag).delete()
    repo.session.query(Tag).delete()
    repo.session.query(FileModel).delete()
    repo.session.flush()
    target_file = _add_file(repo, f"{WORKSPACE}/a.txt", size=10, mtime=1000.0)

    # 全部默认裁决
    plan = ImportPlan(workspace=WORKSPACE)
    plan.file_decisions["a.txt"] = [target_file.id]

    summary = commit_import(repo, payload, plan)
    repo.session.commit()

    assert summary.tags_created == 2
    assert summary.tags_reused == 0
    assert summary.files_linked == 1

    # 标签父子关系应正确重建
    new_tags = repo.session.query(Tag).all()
    by_name = {t.name: t for t in new_tags}
    assert by_name["重要"].parent_id == by_name["项目"].id
    # 文件应关联到子标签
    links = repo.session.query(FileTag).all()
    assert len(links) == 1
    assert links[0].tag_id == by_name["重要"].id


def test_commit_import_reuses_existing_tag_on_skip(repo: Repo):
    _add_tag(repo, "已存在")  # 目标 workspace 已有同名标签

    # 构造仅含一个标签的导入 payload（手动构造，避免依赖 export 当前 DB 状态）
    from app.services.tag_transfer import ExportPayload, ExportedTag

    payload = ExportPayload(
        schema_version=EXPORT_SCHEMA_VERSION,
        exported_at="",
        source_workspace="other",
        tags=(ExportedTag(
            export_id="t1",
            name="已存在",
            color=None,
            icon=None,
            description=None,
            parent_export_id=None,
        ),),
        files=(),
    )
    plan = ImportPlan(workspace=WORKSPACE)
    plan.tag_strategy["t1"] = "skip"

    summary = commit_import(repo, payload, plan)
    repo.session.commit()

    assert summary.tags_created == 0
    assert summary.tags_reused == 1
    # 仍只有一条标签
    assert repo.session.query(Tag).count() == 1
