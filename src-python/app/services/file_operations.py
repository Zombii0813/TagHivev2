"""文件系统操作的失败补偿及回收站语义。"""

from contextlib import contextmanager
from pathlib import Path
import ctypes
import platform
import shutil
import subprocess
import threading
from functools import wraps

filesystem_lock = threading.RLock()


def serialized_filesystem(function):
    """串行化磁盘变更与监控索引同步，防止自身操作产生重复索引。"""
    @wraps(function)
    def wrapped(*args, **kwargs):
        """在同一可重入锁内执行操作。"""
        with filesystem_lock:
            return function(*args, **kwargs)
    return wrapped



def trash_path(path: Path) -> None:
    """把文件或目录移至回收站；失败时保留原物，不降级为永久删除。"""
    if platform.system() == "Windows":
        from ctypes import wintypes

        class FileOperation(ctypes.Structure):
            """Windows 文件操作结构。"""
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                        ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                        ("fFlags", wintypes.WORD), ("aborted", wintypes.BOOL),
                        ("mapping", wintypes.LPVOID), ("title", wintypes.LPCWSTR)]

        operation = FileOperation()
        operation.wFunc = 3
        operation.pFrom = str(path.resolve()) + "\0"
        operation.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400
        call = ctypes.windll.shell32.SHFileOperationW
        call.argtypes = [ctypes.POINTER(FileOperation)]
        call.restype = ctypes.c_int
        result = call(ctypes.byref(operation))
        if result or operation.aborted:
            raise OSError(f"回收站操作失败或被取消 ({result})")
    elif platform.system() == "Darwin":
        subprocess.run(["osascript", "-e", 'on run argv\n tell application "Finder" to delete POSIX file (item 1 of argv)\nend run', str(path)], check=True, capture_output=True)
    else:
        try:
            subprocess.run(["gio", "trash", str(path)], check=True, capture_output=True)
        except FileNotFoundError:
            subprocess.run(["trash-put", str(path)], check=True, capture_output=True)
    if path.exists():
        raise OSError("回收站操作后源路径仍存在")


@contextmanager
def filesystem_transaction(repo):
    """提交数据库；发生异常时逆序补偿本次磁盘操作。

    Args:
        repo: 独占当前操作的数据库仓储。

    Yields:
        记录 (源路径或 None, 唯一目标路径) 的补偿列表。
    """
    changes = []
    filesystem_lock.acquire()
    try:
        yield changes
        repo.session.commit()
    except Exception as error:
        repo.session.rollback()
        failures = []
        for source, target in reversed(changes):
            try:
                if source is not None:
                    if target.exists() and not source.exists():
                        shutil.move(str(target), str(source))
                    elif target.exists() and source.exists():
                        # 跨盘移动可能在删除源目录时失败，先恢复完整源树。
                        if target.is_dir():
                            shutil.copytree(target, source, dirs_exist_ok=True)
                            shutil.rmtree(target)
                        else:
                            target.unlink()
                elif target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
            except OSError as recovery_error:
                failures.append(f"{target} → {source}: {recovery_error}")
        if failures:
            raise RuntimeError(f"{error}; 补偿失败，请保留现场并重新扫描: {'; '.join(failures)}") from error
        raise

    finally:
        filesystem_lock.release()
