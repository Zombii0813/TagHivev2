"""用隔离合成库测量搜索首屏及深页，不访问用户文件。"""

import json
import math
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src-python'))
from sqlalchemy import insert, text
from app.db import session as db
from app.db.models import File
from app.db.repo import Repo
from app.api.routes import _build_search_result
from app.api.models import SearchQueryDTO


def measure(repo, offset):
    """记录首次请求及七次重复请求的 P50/P95（非 OS 冷缓存）。"""
    samples = []
    for _ in range(8):
        repo.session.expunge_all()
        start = time.perf_counter()
        result = _build_search_result(SearchQueryDTO(root='/benchmark', sort_by='name', offset=offset, limit=500), repo)
        assert len(result.files) == 500
        samples.append((time.perf_counter() - start) * 1000)
    warm = sorted(samples[1:])
    return {'first_request_ms': round(samples[0], 2), 'p50_ms': round(statistics.median(warm), 2),
            'p95_ms': round(warm[math.ceil(.95 * len(warm)) - 1], 2), 'samples': 7}


def main():
    """生成两种规模的基准，并比较自然排序索引效果。"""
    rows = []
    (ROOT / '.audit-tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='optimization-benchmark-', dir=ROOT / '.audit-tmp', ignore_cleanup_errors=True) as directory:
        db.init_db(Path(directory) / 'benchmark.db')
        with db.get_session() as session:
            repo = Repo(session)
            previous = 0
            for count in [10000, 100000]:
                for start in range(previous, count, 1000):
                    session.execute(insert(File), [dict(path=f'/benchmark/folder-{i % 40}/file-{i}.png',
                        parent_dir=f'/benchmark/folder-{i % 40}', name=f'file-{i}.png', type='image',
                        size=i, modified_at=1700000000.) for i in range(start, min(count, start + 1000))])
                session.commit()
                for indexed in [False, True]:
                    if indexed:
                        session.execute(text('CREATE INDEX IF NOT EXISTS idx_files_name_natural ON files(name COLLATE "NATURAL", id)'))
                    else:
                        session.execute(text('DROP INDEX IF EXISTS idx_files_name_natural'))
                    session.commit()
                    for offset in [0, count - 500]:
                        row = dict(count=count, offset=offset, natural_index=indexed, **measure(repo, offset))
                        rows.append(row); print(json.dumps(row), flush=True)
                previous = count
        db._engine.dispose()
        db._engine = None; db._engine_path = None
    output = ROOT / 'reports' / 'optimization-benchmark-2026-11-12.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({'python': platform.python_version(), 'platform': platform.platform(),
        'scope': 'search API builder including count, 500 DTOs and tag query; warm process/OS cache; 7 repeated samples',
        'results': rows}, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
