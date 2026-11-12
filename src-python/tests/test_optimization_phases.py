"""第二轮分阶段优化的行为回归。"""

import sqlite3
import threading
import time
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import event, text

from app.core.search import SearchQuery
from app.db import session as db
from app.utils.file_names import validate_name
from app.utils.ignore import should_ignore
from tests.conftest import make_meta


def test_literal_substrings_and_wildcards(repo):
    """长短词保持子串语义，通配符按字面匹配。"""
    names = ['port map.png', 'report.pdf', 'airport.jpg', 'a_b.txt', 'axb.txt', '10%.txt', '中文报告文件.txt']
    for name in names:
        repo.upsert_file(make_meta('/demo/' + name))
    repo.session.commit()
    for term in ['por', 'port']:
        assert len(repo.search(SearchQuery(text=term))) == 3
    assert len(repo.search(SearchQuery(text='_'))) == 1
    assert len(repo.search(SearchQuery(text='%'))) == 1
    assert len(repo.search(SearchQuery(text='文报告'))) == 1


@pytest.mark.parametrize('name', ['../out.txt', '..\\out.txt', 'C:bad', 'nul.txt', 'a.', 'a\x00b', ' a'])
def test_names_reject_paths_and_reserved_values(name):
    """后端拒绝路径逃逸及系统保留名称。"""
    with pytest.raises(ValueError):
        validate_name(name)


def test_root_relative_ignore(tmp_path):
    """完整段匹配不会误伤含 git 子串的工作区及目录。"""
    root = tmp_path / 'company.github.io'
    assert not should_ignore(root / '.github' / 'test.yml', root)
    assert not should_ignore(root / 'design.git-assets' / 'a.png', root)
    assert should_ignore(root / '.git' / 'config', root)
    assert should_ignore(root / 'cache.db', root)


def test_database_pragmas_and_cascade(repo):
    """连接启用 WAL 和外键，删除实体自动清理关联。"""
    from app.db.models import Tag, FileTag
    file = repo.upsert_file(make_meta('/a.png'))
    tag = Tag(name='a')
    repo.session.add(tag)
    repo.session.flush()
    repo.session.add(FileTag(file_id=file.id, tag_id=tag.id))
    repo.session.commit()
    assert repo.session.execute(text('PRAGMA journal_mode')).scalar() == 'wal'
    assert repo.session.execute(text('PRAGMA foreign_keys')).scalar() == 1
    assert repo.session.execute(text('PRAGMA user_version')).scalar() == db.SCHEMA_VERSION
    repo.session.execute(text('DELETE FROM files WHERE id=:id'), {'id': file.id})
    repo.session.commit()
    assert repo.session.execute(text('SELECT count(*) FROM file_tags')).scalar() == 0


def test_legacy_migration_preserves_hierarchy_and_repairs_orphans(tmp_db):
    """迁移保留有效关联和父标签，仅移除孤儿关联。"""
    db._engine.dispose()
    with sqlite3.connect(tmp_db) as conn:
        conn.create_collation("NATURAL", db._natural_collation)
        conn.executescript("""
            PRAGMA foreign_keys=OFF;
            PRAGMA user_version=0;
            CREATE UNIQUE INDEX tags_legacy_name_unique ON tags(name);
            INSERT INTO files(id,path,name,size,type) VALUES(1,'/a.png','a.png',0,'image');
            INSERT INTO tags(id,name,parent_id) VALUES(1,'parent',NULL),(2,'child',1);
            INSERT INTO file_tags VALUES(1,2),(999,2);
        """)
    db._ensure_schema()
    db._ensure_schema()
    with db.get_session() as session:
        assert session.execute(text('SELECT parent_id FROM tags WHERE id=2')).scalar() == 1
        assert session.execute(text('SELECT count(*) FROM file_tags')).scalar() == 1
        assert session.execute(text('PRAGMA foreign_key_check')).all() == []


def test_exif_orientation_shared_by_generators(tmp_path):
    """两个生成入口都在缩放前校正 EXIF 方向。"""
    from app.services.thumbnail_service import ThumbnailService
    from app.core.async_thumbnail import MultiSizeThumbnailGenerator
    source = tmp_path / 'rotated.jpg'
    image = Image.new('RGB', (80, 40), 'red')
    exif = Image.Exif(); exif[274] = 6
    image.save(source, exif=exif)
    for index, generator in enumerate([ThumbnailService(tmp_path / 'sync'), MultiSizeThumbnailGenerator(tmp_path / 'async')]):
        result = generator.generate_thumbnail(str(source), 'medium')
        assert result
        with Image.open(result.removeprefix('file://')) as thumb:
            # 旋转后为竖图：顶部中间是红色，左侧中间是画布。
            assert thumb.getpixel((120, 10))[0] > 200
            assert thumb.getpixel((10, 120))[0] < 80


def test_unchanged_scan_does_not_update(repo):
    """相同签名的再次扫描不发送 UPDATE。"""
    meta = make_meta('/demo/a.png')
    file = repo.upsert_file(meta)
    repo.session.commit()
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        """记录数据库写入语句。"""
        if statement.lstrip().upper().startswith('UPDATE'):
            statements.append(statement)
    event.listen(db._engine, 'before_cursor_execute', record)
    try:
        repo.bulk_upsert_files_fast([meta], {meta.path.as_posix(): file.id})
        repo.session.commit()
        assert statements == []
    finally:
        event.remove(db._engine, 'before_cursor_execute', record)


def test_thumbnail_priority_dedup_and_bounded_results(tmp_path):
    """线程池繁忙时高优先级先执行，重复任务不会挤占队列。"""
    from app.core.async_thumbnail import AsyncThumbnailGenerator, Priority
    generator = AsyncThumbnailGenerator(tmp_path, max_workers=1)
    gate = threading.Event()
    started = threading.Event()
    order = []
    def render(path, size):
        """阻塞首任务以检查等待队列的实际执行顺序。"""
        order.append(path)
        started.set()
        if path == 'first':
            gate.wait(5)
        return path
    generator._generate_thumbnail = render
    generator.start()
    try:
        generator.generate_async('first')
        assert started.wait(2)
        generator.generate_async('low', priority=Priority.LOW)
        generator.generate_async('high', priority=Priority.HIGH)
        generator.generate_async('high', priority=Priority.HIGH)
        assert generator.task_queue.qsize() == 2
        assert len(generator._active) == 1
        gate.set()
        deadline = time.monotonic() + 5
        while generator.get_stats()['completed'] < 3 and time.monotonic() < deadline:
            time.sleep(.01)
        assert order == ['first', 'high', 'low']
        assert generator.result_queue.maxsize == 256
    finally:
        gate.set(); generator.stop()


def test_static_thumbnail_stats_is_reachable():
    """静态 stats 路由不能被文件 ID 动态路由遮挡。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.thumbnails import router
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as client:
        assert client.get('/api/thumbnails/stats').status_code == 200


def test_unknown_duration_last_and_stable_ties(repo):
    """正反向时长排序均将未知值置末，同值保持 ID 次序。"""
    rows = [repo.upsert_file(make_meta(f'/demo/{i}.mp4')) for i in range(4)]
    rows[1].duration = 10; rows[2].duration = 10; rows[3].duration = 20
    repo.session.commit()
    for descending, expected in [(False, [1, 2, 3, 0]), (True, [3, 1, 2, 0])]:
        result = repo.search_with_offset(SearchQuery(sort_by='duration', sort_desc=descending), limit=10)
        assert [r.file_id for r in result.items] == [rows[i].id for i in expected]
    assert repo.search_with_offset(SearchQuery(sort_by='tags'), limit=10).items


def test_cancelled_scan_keeps_unvisited_records(repo, tmp_path, monkeypatch):
    """扫描中途取消不会清理尚未枚举到的记录。"""
    from app.services.scan_service import ScanService
    from app.core.indexer import build_file_meta
    root = tmp_path / 'demo'; root.mkdir()
    file = root / 'a.txt'; file.write_text('a')
    row = repo.upsert_file(build_file_meta(file)); repo.session.commit()
    file.unlink()
    cancel = threading.Event()
    def entries(*args):
        """模拟枚举进行到一半收到取消。"""
        cancel.set()
        return iter(())
    monkeypatch.setattr('app.services.scan_service.UltraFastFileScanner.scan_directory_stream', entries)
    ScanService(repo.session).scan_workspace(root, cancel=cancel)
    assert repo.get_file_by_id(row.id) is not None


def test_thumbnail_queue_eviction_and_negative_cache(tmp_path):
    """视口淘汰释放排队记录，失败键在有效期内不重复生成。"""
    from concurrent.futures import Future
    from app.core.async_thumbnail import AsyncThumbnailGenerator, ThumbnailTask
    generator = AsyncThumbnailGenerator(tmp_path)
    try:
        generator.generate_async('old'); generator.generate_async('current')
        generator.set_visible_files(['current'])
        assert generator.task_queue.qsize() == 1
        assert len(generator._pending) == 1
        for i in range(300):
            task = ThumbnailTask(1, str(i), 'medium', key=f'key-{i}')
            future = Future(); future.set_result(None)
            generator._on_task_complete(future, task)
        assert generator.result_queue.qsize() == 256
        assert len(generator._negative) == 300
    finally:
        generator.stop()


def test_media_coverage_and_probe_snapshot(repo, tmp_path, monkeypatch):
    """补探测范围、签名校验和取消均在独立任务中生效。"""
    from app.api import media
    from app.utils.media_info import MediaInfoResult
    root = tmp_path / 'media'; root.mkdir()
    first = repo.upsert_file(make_meta((root / 'a.mp4').as_posix(), type_='video'))
    second = repo.upsert_file(make_meta((root / 'b.mp4').as_posix(), type_='video'))
    repo.session.commit()
    scope = media.MediaScope(root=root.as_posix())
    assert media.coverage.__wrapped__(scope, repo) == {'total': 2, 'probed': 0, 'known': 0}
    entered, release = threading.Event(), threading.Event()
    def probe(path):
        """阻塞首项，确认取消不继续处理第二项。"""
        entered.set(); release.wait(3)
        return MediaInfoResult(duration=12)
    monkeypatch.setattr(media, 'extract_media_info', probe)
    media.start_probe.__wrapped__(scope, repo)
    assert entered.wait(2)
    media.cancel_probe(); release.set()
    deadline = time.monotonic() + 4
    while media.probe_status()['running'] and time.monotonic() < deadline:
        time.sleep(.01)
    repo.session.expire_all()
    assert repo.get_file_by_id(first.id).duration == 12
    assert repo.get_file_by_id(second.id).duration is None
    assert media.probe_status()['cancelled'] is True
    assert media.coverage.__wrapped__(scope, repo)['known'] == 1


@pytest.mark.asyncio
async def test_scan_queue_serializes_and_reports_remaining(tmp_db, tmp_path, monkeypatch):
    """多个工作区扫描串行执行，取消和剩余数对应每个任务。"""
    import asyncio
    from app.api import websocket as ws
    from app.services.scan_service import ScanService
    root_a, root_b = tmp_path / 'a', tmp_path / 'b'
    root_a.mkdir(); root_b.mkdir()
    entered, release = threading.Event(), threading.Event()
    active = 0
    maximum = 0
    events = []
    def scan(self, path, on_progress=None, cancel=None):
        """记录并发数并等待测试解除阻塞。"""
        nonlocal active, maximum
        active += 1; maximum = max(maximum, active)
        entered.set(); release.wait(3)
        active -= 1
        return 0
    async def emit(name, data, **kwargs):
        """保存广播，验证任务完成后的剩余数量。"""
        events.append((name, data))
    async def broadcast(*args):
        """跳过与队列无关的目录广播。"""
    monkeypatch.setattr(ScanService, 'scan_workspace', scan)
    monkeypatch.setattr(ws.sio, 'emit', emit)
    monkeypatch.setattr(ws, 'broadcast_folder_tree_changed', broadcast)
    monkeypatch.setattr(ws, '_scan_queue_lock', asyncio.Lock())
    tasks = [asyncio.create_task(ws.start_scan('demo', {'path': str(root)})) for root in [root_a, root_b]]
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        await ws.cancel_scan('demo', {})
        release.set()
        await asyncio.gather(*tasks)
        completed = [data for name, data in events if name == 'scan_completed']
        assert maximum == 1
        assert [data['remaining'] for data in completed] == [1, 0]
        assert all(data['cancelled'] for data in completed)
        assert len({data['task_id'] for data in completed}) == 2
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)

