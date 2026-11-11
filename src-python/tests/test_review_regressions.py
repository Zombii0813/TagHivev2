"""审查问题的隔离回归测试，所有磁盘及数据库操作限定于 tmp_path。"""

import asyncio
import json
from pathlib import Path
import threading
import time

import httpx
import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import event

from app.api import routes
from app.api.models import (
    FileMoveRequestDTO, FileCopyRequestDTO, FileImportRequestDTO,
    FolderDeleteRequestDTO, FolderMoveRequestDTO, SearchQueryDTO, TagUpdateDTO,
)
from app.core.indexer import build_file_meta
from app.core.search import SearchQuery
from app.db.models import Tag
from app.services.scan_service import ScanService


def indexed_file(repo, path, tags=()):
    """创建并登记隔离文件，返回带稳定 ID 的记录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"test")
    row = repo.upsert_file(build_file_meta(path))
    row.tags = list(tags)
    repo.session.commit()
    return row


def test_f01_scan_keeps_sibling_workspace(repo, tmp_path):
    """扫描 work 不清理 work2 内的索引和标签。"""
    root = tmp_path / "work"
    root.mkdir()
    tag = Tag(name="keep")
    repo.session.add(tag)
    repo.session.flush()
    sibling = indexed_file(repo, tmp_path / "work2" / "b.txt", [tag])
    ScanService(repo.session).scan_workspace(root)
    repo.session.expire_all()
    assert Path(sibling.path).exists()
    assert repo.get_file_by_id(sibling.id).tags[0].id == tag.id
    assert not ScanService._is_under_root(sibling.path, root)
    assert ScanService._is_under_root((root / "a").as_posix().upper(), Path(str(root).upper()))


@pytest.mark.parametrize("failure", ["enumeration", "metadata", "permission"])
def test_f02_partial_scan_keeps_existing_files(repo, tmp_path, monkeypatch, failure):
    """枚举、元数据或权限异常不能清除仍存在的文件。"""
    root = tmp_path / "work"
    row = indexed_file(repo, root / "sub" / "a.txt")
    service = ScanService(repo.session)
    if failure == "enumeration":
        monkeypatch.setattr("app.services.scan_service.UltraFastFileScanner.scan_directory_stream", lambda *args: iter(()))
        service.scan_workspace(root)
    elif failure == "metadata":
        monkeypatch.setattr(service, "_process_entry_fast", lambda entry: None)
        service.scan_workspace(root)
    else:
        original = Path.stat

        def stat(path, *args, **kwargs):
            """模拟单个文件的拒绝访问。"""
            if path == Path(row.path):
                raise PermissionError("injected")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", stat)
        service._cleanup_stale_files(repo, root, set())
    assert repo.get_file_by_id(row.id) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("folder", [False, True])
async def test_f03_trash_failure_keeps_disk_and_index(repo, tmp_path, monkeypatch, folder):
    """回收站失败时返回错误，文件和标签均保留。"""
    row = indexed_file(repo, tmp_path / "work" / "sub" / "a.txt")

    def fail(path):
        """模拟回收站失败。"""
        raise OSError("injected trash failure")

    monkeypatch.setattr(routes, "trash_path", fail)
    with pytest.raises(HTTPException) as error:
        if folder:
            await routes.delete_folder(FolderDeleteRequestDTO(root_path=str(tmp_path / "work"), folder_path=str(Path(row.path).parent)), repo=repo)
        else:
            await routes.delete_file(row.id, repo=repo)
    assert error.value.status_code == 409
    assert Path(row.path).exists()
    assert repo.get_file_by_id(row.id) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["move", "copy", "import"])
async def test_f04_second_failure_compensates_batch(repo, tmp_path, monkeypatch, operation):
    """第二项失败时，已完成的第一项磁盘及数据库变更一同撤回。"""
    first = indexed_file(repo, tmp_path / "source" / "a.txt")
    second = indexed_file(repo, tmp_path / "source" / "b.txt")
    first_id, second_id = first.id, second.id
    originals = [first.path, second.path]
    target = tmp_path / "target"
    target.mkdir()
    real_call = routes.shutil.copy2 if operation == "copy" else routes.shutil.move
    calls = 0

    def fail_second(source, destination, *args, **kwargs):
        """只让第二个正向操作失败，允许补偿正常执行。"""
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second item failure")
        return real_call(source, destination, *args, **kwargs)

    monkeypatch.setattr(routes.shutil, "copy2" if operation == "copy" else "move", fail_second)
    with pytest.raises(HTTPException):
        if operation == "move":
            await routes.move_files(FileMoveRequestDTO(file_ids=[first_id, second_id], target_dir=str(target)), repo=repo)
        elif operation == "copy":
            await routes.copy_files(FileCopyRequestDTO(file_ids=[first_id, second_id], target_dir=str(target)), repo=repo)
        else:
            await routes.import_files_to_directory(FileImportRequestDTO(paths=originals, target_dir=str(target)), repo=repo)
    assert all(Path(path).exists() for path in originals)
    assert not list(target.iterdir())
    assert [repo.get_file_by_id(value).path for value in [first_id, second_id]] == originals


@pytest.mark.asyncio
async def test_f04_database_failure_restores_folder(repo, tmp_path, monkeypatch):
    """数据库提交失败时，整棵目录被恢复到原位置。"""
    row = indexed_file(repo, tmp_path / "source" / "sub" / "a.txt")
    original = row.path
    target = tmp_path / "target"
    target.mkdir()

    def fail():
        """模拟提交故障。"""
        raise OSError("injected database commit failure")

    monkeypatch.setattr(repo.session, "commit", fail)
    with pytest.raises(OSError):
        await routes.move_folder(FolderMoveRequestDTO(source_path=str(tmp_path / "source"), target_dir=str(target)), repo=repo)
    assert Path(original).exists()
    assert not list(target.iterdir())
    assert repo.get_file_by_id(row.id).path == original


def test_f05_external_moves_preserve_id_and_tags(repo, tmp_path):
    """外部文件与目录移动保留原 ID、标签，删除目录清理其子索引。"""
    from app.api.websocket import _apply_file_change
    tag = Tag(name="keep")
    repo.session.add(tag)
    repo.session.flush()
    row = indexed_file(repo, tmp_path / "source" / "sub" / "a.txt", [tag])
    original_id = row.id
    source, target = tmp_path / "source", tmp_path / "renamed"
    source.rename(target)
    _apply_file_change(source, "moved", target)
    repo.session.expire_all()
    assert repo.get_file_by_id(original_id).path == (target / "sub" / "a.txt").as_posix()
    assert repo.get_file_by_id(original_id).tags[0].id == tag.id
    import shutil
    shutil.rmtree(target)
    _apply_file_change(target, "directory", None)
    repo.session.expire_all()
    assert repo.get_file_by_id(original_id) is None


@pytest.mark.asyncio
async def test_f05_watchdog_thread_dispatches_to_main_loop(tmp_path, monkeypatch):
    """真实线程触发监控回调时，协程运行于主事件循环。"""
    from app.api import websocket as ws
    root = tmp_path / "work"
    root.mkdir()
    observed = asyncio.Event()
    main_thread = threading.get_ident()

    async def handle(*args):
        """记录实际派发线程。"""
        assert threading.get_ident() == main_thread
        observed.set()

    class Watch:
        """用真实工作线程模拟 watchdog 派发。"""
        def start(self, root, **callbacks):
            """在线程池内触发回调。"""
            callbacks["on_change"](root / "a.txt")
        def stop(self):
            """结束模拟监控。"""

    monkeypatch.setattr(ws, "WatchService", Watch)
    monkeypatch.setattr(ws, "_handle_file_change", handle)
    await ws.subscribe_workspace("test", {"paths": [str(root)]})
    await asyncio.wait_for(observed.wait(), 2)
    await ws.unsubscribe_workspace("test", {})


@pytest.mark.asyncio
async def test_f06_f12_hierarchy_validation_and_explicit_null(repo):
    """拒绝循环、缺失和跨工作区父标签；省略保留、null 清除。"""
    parent = Tag(name="parent", workspace="A")
    foreign = Tag(name="foreign", workspace="B")
    repo.session.add_all([parent, foreign])
    repo.session.flush()
    child = Tag(name="child", workspace="A", parent_id=parent.id)
    repo.session.add(child)
    repo.session.commit()
    for target in [parent.id, child.id, foreign.id, 99999]:
        with pytest.raises(HTTPException) as error:
            await routes.update_tag(parent.id, TagUpdateDTO(parent_id=target), repo=repo)
        assert error.value.status_code == 400
    await routes.update_tag(child.id, TagUpdateDTO(description="updated"), repo=repo)
    assert child.parent_id == parent.id
    await routes.update_tag(child.id, TagUpdateDTO(parent_id=None), repo=repo)
    assert child.parent_id is None


@pytest.mark.asyncio
async def test_f12_atomic_delete_promotes_nested_selection(repo):
    """批量删掉连续父层级时，未选中的后代提升到最近存活祖先。"""
    tags = []
    for index in range(4):
        tag = Tag(name=str(index), parent_id=tags[-1].id if tags else None)
        repo.session.add(tag)
        repo.session.flush()
        tags.append(tag)
    repo.session.commit()
    ids = [tag.id for tag in tags]
    await routes.delete_tags_atomic({"ids": ids[1:3], "mode": "promote"}, repo=repo)
    repo.session.expire_all()
    assert repo.session.get(Tag, ids[3]).parent_id == ids[0]
    assert repo.session.get(Tag, ids[1]) is None


@pytest.mark.asyncio
async def test_f07_rest_socket_and_media_authentication():
    """未授权、本机恶意来源及错误实例凭据均被拒绝。"""
    from app.main import app
    from app.security import SESSION_TOKEN, INSTANCE_ID
    from app.api.websocket import connect, disconnect
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        assert (await client.get("/api/health")).status_code == 401
        assert (await client.get("/api/session", headers={"Origin": "https://untrusted.example"})).status_code == 403
        trusted = {"Authorization": f"Bearer {SESSION_TOKEN}", "Origin": "http://localhost:5173"}
        response = await client.get("/api/health", headers=trusted)
        assert response.status_code == 200 and response.json()["instance_id"] == INSTANCE_ID
        assert (await client.get("/api/health", headers={**trusted, "Origin": "https://untrusted.example"})).status_code == 403
        assert (await client.get("/api/files/1/preview?session=wrong")).status_code == 401
        assert (await client.delete(f"/api/files/1?session={SESSION_TOKEN}")).status_code == 401
        assert (await client.get("/api/health", headers={**trusted, "Host": "rebinding.example"})).status_code == 400
    assert await connect("unauthorized", {}, {"token": "wrong"}) is False
    await connect("authorized", {}, {"token": SESSION_TOKEN})
    await disconnect("authorized")


@pytest.mark.parametrize("match_all", [False, True])
def test_f10_count_matches_full_tag_and_scope_filters(repo, tmp_path, match_all):
    """OR 去重，AND 保留关键词、类型和目录的全部条件。"""
    tags = [Tag(name="one"), Tag(name="two")]
    repo.session.add_all(tags)
    repo.session.flush()
    indexed_file(repo, tmp_path / "A" / "wanted.txt", tags)
    indexed_file(repo, tmp_path / "B" / "wanted.txt", tags)
    query = SearchQuery(text="wanted", root=str(tmp_path / "A"), types=("other",), tags=tuple(tag.id for tag in tags), match_all_tags=match_all, use_fts=False)
    # txt 被分类为 doc，取实际类型验证组合条件。
    query = SearchQuery(**{**query.__dict__, "types": (repo.get_file_by_path((tmp_path / "A" / "wanted.txt").as_posix()).type,)})
    assert repo.count_search(query) == len(repo.search_with_offset(query).items) == 1


@pytest.mark.parametrize("name", ["a_b", "a%b", "a!b"])
def test_f11_literal_path_prefix(repo, tmp_path, name):
    """路径中的 SQL 通配符被视为字面字符。"""
    first = indexed_file(repo, tmp_path / name / "a.txt")
    indexed_file(repo, tmp_path / "axb" / "b.txt")
    query = SearchQuery(root=str(tmp_path / name))
    assert [row.file_id for row in repo.search(query)] == [first.id]
    assert repo.count_search(query) == 1


@pytest.mark.asyncio
async def test_f11_delete_folder_cannot_purge_similar_sibling(repo, tmp_path, monkeypatch):
    """删除含下划线的目录不会清理相似目录的索引。"""
    import shutil
    inside = indexed_file(repo, tmp_path / "work" / "a_b" / "a.txt")
    outside = indexed_file(repo, tmp_path / "work" / "axb" / "b.txt")
    inside_id, outside_id = inside.id, outside.id
    monkeypatch.setattr(routes, "trash_path", shutil.rmtree)
    await routes.delete_folder(FolderDeleteRequestDTO(root_path=str(tmp_path / "work"), folder_path=str(tmp_path / "work" / "a_b")), repo=repo)
    assert repo.get_file_by_id(inside_id) is None
    assert repo.get_file_by_id(outside_id) is not None
    assert Path(outside.path).exists()


def test_f06_import_rejects_cycle_before_writing(repo):
    """标签包中的循环父关系在任何写入发生前被拒绝。"""
    from app.services.tag_transfer import ExportPayload, ExportedTag, ImportPlan, ThpackFormatError, commit_import
    payload = ExportPayload(2, "", "A", (
        ExportedTag("a", "a", None, None, None, "b"),
        ExportedTag("b", "b", None, None, None, "a"),
    ), ())
    with pytest.raises(ThpackFormatError):
        commit_import(repo, payload, ImportPlan(workspace="A"))
    assert repo.list_tags() == []


@pytest.mark.parametrize("generator_name", ["sync", "async"])
def test_f13_same_path_replacement_changes_thumbnail(tmp_path, generator_name):
    """同路径红图替换蓝图后，两套缩略图生成器都返回新内容。"""
    from app.services.thumbnail_service import ThumbnailService
    from app.core.async_thumbnail import MultiSizeThumbnailGenerator
    source = tmp_path / "source.png"
    Image.new("RGB", (32, 32), "red").save(source)
    service = ThumbnailService(tmp_path / "cache") if generator_name == "sync" else MultiSizeThumbnailGenerator(tmp_path / "cache")
    generate = service.generate_thumbnail
    generate(str(source), "medium")
    old_path = service.get_thumbnail_path(str(source), "medium")
    old_bytes = old_path.read_bytes()
    Image.new("RGB", (32, 32), "blue").save(source)
    generate(str(source), "medium")
    new_path = service.get_thumbnail_path(str(source), "medium")
    assert old_path != new_path and old_bytes != new_path.read_bytes()
    assert not list((tmp_path / "cache").glob("*.tmp"))


@pytest.mark.asyncio
async def test_f14_copy_does_not_block_event_loop(repo, tmp_path, monkeypatch, record_property):
    """注入 200ms 磁盘阻塞，事件循环仍可按时执行计时器。"""
    row = indexed_file(repo, tmp_path / "source" / "a.txt")
    target = tmp_path / "target"
    target.mkdir()
    copy = routes.shutil.copy2

    def slow_copy(*args, **kwargs):
        """模拟慢速磁盘。"""
        time.sleep(0.2)
        return copy(*args, **kwargs)

    monkeypatch.setattr(routes.shutil, "copy2", slow_copy)
    started = time.perf_counter()
    task = asyncio.create_task(routes.copy_files(FileCopyRequestDTO(file_ids=[row.id], target_dir=str(target)), repo=repo))
    await asyncio.sleep(0.02)
    delay = (time.perf_counter() - started) * 1000
    await task
    record_property("callback_delay_ms", round(delay, 2))
    assert delay < 150


def test_f15_500_results_have_bounded_tag_queries(repo, tmp_path, record_property):
    """两万条索引返回 500 文件时，SQL 次数不随文件数线性增长。"""
    from tests.conftest import make_meta
    repo.bulk_upsert_files_fast([make_meta((tmp_path / f"f{index}.jpg").as_posix()) for index in range(20000)], {})
    repo.session.commit()
    queries = []

    def count(connection, cursor, statement, parameters, context, executemany):
        """统计 SELECT。"""
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    engine = repo.session.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    samples = []
    try:
        for _ in range(5):
            repo.session.expire_all()
            queries.clear()
            started = time.perf_counter()
            result = routes._build_search_result(SearchQueryDTO(limit=500), repo)
            samples.append(round((time.perf_counter() - started) * 1000, 2))
            assert result.total == 20000 and len(result.files) == 500
            assert len(queries) <= 5
    finally:
        event.remove(engine, "before_cursor_execute", count)
    import statistics
    record_property("select_statements", len(queries))
    record_property("milliseconds", statistics.median(samples))
    record_property("samples_ms", json.dumps(samples))


def test_f17_scan_invalidates_tree_cache(repo, tmp_path):
    """扫描完成立即移除缓存的旧目录树。"""
    from app.core.query_cache import get_query_cache
    root = tmp_path / "work"
    root.mkdir()
    cache = get_query_cache()
    key = f"folder:tree:{root.as_posix()}"
    cache.set(key, {"old": True}, ttl=300)
    ScanService(repo.session).scan_workspace(root)
    assert cache.get(key) is None


@pytest.mark.asyncio
async def test_f18_registered_roots_scope_files_tags_and_stats(repo, tmp_path):
    """移除工作区后全局视图仅显示已注册范围，历史数据仍可重用。"""
    a, b = tmp_path / "A", tmp_path / "B"
    ta, tb = Tag(name="a", workspace=a.as_posix()), Tag(name="b", workspace=b.as_posix())
    repo.session.add_all([ta, tb])
    repo.session.flush()
    indexed_file(repo, a / "a.txt", [ta])
    indexed_file(repo, b / "b.txt", [tb])
    query = SearchQuery(roots=(a.as_posix(),))
    assert repo.count_search(query) == 1
    assert repo.count_search(SearchQuery(roots=())) == 0
    tags = await routes.list_tags(roots=json.dumps([a.as_posix()]), repo=repo)
    assert [tag.id for tag in tags] == [ta.id]
    assert (await routes.get_workspace_stats(roots=json.dumps([a.as_posix()]), repo=repo))["total_files"] == 1
    assert repo.count_search(SearchQuery(roots=(a.as_posix(), b.as_posix()))) == 2
