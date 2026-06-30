"""父进程监控模块。

用于解决打包后 sidecar 成为孤儿进程的问题：当宿主（Tauri 主进程）通过
任务管理器结束、崩溃或强制关机等方式异常退出时，`CloseRequested` 钩子
不会触发，sidecar 将持续运行并锁定安装目录下的文件（如 _internal\\*.dll），
导致安装/卸载时报“TagHive 正在运行”。

本模块启动一个守护线程，持续监控父进程是否存活，一旦父进程消失即立即
退出当前进程，从根本上避免孤儿残留。
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 环境变量名：由 Rust 端启动 sidecar 时写入其自身 PID
PARENT_PID_ENV = "TAGHIVE_PARENT_PID"

# 轮询间隔（秒）
_POLL_INTERVAL = 2.0


def _wait_parent_exit_windows(parent_pid: int) -> None:
    """在 Windows 上阻塞等待父进程退出。

    使用 OpenProcess + WaitForSingleObject 等待父进程句柄进入有信号状态
    （即进程结束）。若无法打开句柄（父进程已不存在或权限不足），则退化为
    轮询模式。

    Args:
        parent_pid: 父进程 PID。
    """
    import ctypes
    from ctypes import wintypes

    SYNCHRONIZE = 0x00100000
    WAIT_OBJECT_0 = 0x00000000
    INFINITE = 0xFFFFFFFF

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

    handle = kernel32.OpenProcess(SYNCHRONIZE, False, parent_pid)
    if not handle:
        # 打不开句柄：可能父进程已退出，回退到轮询模式确认
        logger.warning(
            "无法打开父进程句柄 (pid=%s, err=%s)，回退到轮询模式",
            parent_pid,
            ctypes.get_last_error(),
        )
        _poll_parent_exit(parent_pid)
        return

    try:
        # 阻塞直到父进程结束
        kernel32.WaitForSingleObject(handle, INFINITE)
    finally:
        kernel32.CloseHandle(handle)


def _poll_parent_exit(parent_pid: int) -> None:
    """跨平台轮询等待父进程退出。

    通过 os.kill(pid, 0) 探测进程是否存活；进程不存在时抛出 OSError。

    Args:
        parent_pid: 父进程 PID。
    """
    while True:
        try:
            os.kill(parent_pid, 0)
        except OSError:
            # 父进程已不存在
            return
        time.sleep(_POLL_INTERVAL)


def _watch_loop(parent_pid: int) -> None:
    """监控线程主体：等待父进程退出后强制结束自身。

    Args:
        parent_pid: 父进程 PID。
    """
    logger.info("父进程监控已启动 (parent_pid=%s)", parent_pid)

    if sys.platform == "win32":
        _wait_parent_exit_windows(parent_pid)
    else:
        _poll_parent_exit(parent_pid)

    # 父进程已退出，立即终止自身，避免成为孤儿
    logger.warning("检测到父进程 (pid=%s) 已退出，sidecar 即将自我终止", parent_pid)
    # 使用 os._exit 而非 sys.exit：跳过清理与 atexit，确保即时退出，
    # 不会因为 uvicorn / 后台线程阻塞而残留
    os._exit(0)


def start_parent_watchdog() -> Optional[threading.Thread]:
    """启动父进程监控守护线程。

    从环境变量 ``TAGHIVE_PARENT_PID`` 读取父进程 PID；未设置或非法时不启动
    （例如独立运行、开发调试场景）。

    Returns:
        已启动的守护线程；未启动时返回 None。
    """
    raw = os.environ.get(PARENT_PID_ENV)
    if not raw:
        return None

    try:
        parent_pid = int(raw)
    except ValueError:
        logger.warning("环境变量 %s 非法: %r，跳过父进程监控", PARENT_PID_ENV, raw)
        return None

    if parent_pid <= 0:
        return None

    thread = threading.Thread(
        target=_watch_loop,
        args=(parent_pid,),
        name="parent-watchdog",
        daemon=True,
    )
    thread.start()
    return thread
