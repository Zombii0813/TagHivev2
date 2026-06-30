"""TagHive Sidecar Entry Point for PyInstaller

This is a standalone entry point that doesn't use relative imports.
It's designed to work with PyInstaller to create a bundled executable.
"""

import sys
import os

# PyInstaller multiprocessing support - MUST be first
if getattr(sys, 'frozen', False):
    import multiprocessing
    multiprocessing.freeze_support()

# Add the src-python directory to Python path so 'app' package can be found
if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle (onedir mode)
    # sys.executable is <sidecar_dir>/taghive-sidecar.exe
    # _MEIPASS is the temp extraction dir in onefile, or the exe dir in onedir
    bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
else:
    # Running in normal Python environment
    bundle_dir = os.path.dirname(os.path.abspath(__file__))

# In onedir mode, 'app' package is placed directly inside bundle_dir via --add-data
# In normal mode, 'app' is a sibling of this file (both in src-python/)
if bundle_dir not in sys.path:
    sys.path.insert(0, bundle_dir)


def _fix_dll_search_path():
    """修复打包环境下的 DLL 搜索路径，确保加载随包分发的 OpenSSL DLL。

    问题背景：Windows 加载 _ssl.pyd 时会沿系统 PATH 搜索 libcrypto/libssl，
    而宿主机若安装了其它 Anaconda / MSYS2，其 Library\\bin 中存在版本较旧的
    同名 DLL 且排在 PATH 前面，会被优先加载，缺少导出函数从而触发：
        ImportError: DLL load failed while importing _ssl: 找不到指定的程序

    解决办法：在导入任何依赖 ssl 的模块之前，
        1) 用 os.add_dll_directory() 显式把随包目录加入 DLL 搜索（最高优先级）；
        2) 从进程 PATH 中剔除会造成干扰的第三方 OpenSSL 目录。
    仅在 PyInstaller 冻结环境下生效，普通开发环境不做改动。
    """
    if not getattr(sys, 'frozen', False):
        return

    # onedir 模式下，OpenSSL DLL 与 _ssl.pyd 同在 _internal 目录（即 _MEIPASS）。
    dll_dirs = []
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        dll_dirs.append(meipass)
    exe_dir = os.path.dirname(sys.executable)
    internal_dir = os.path.join(exe_dir, '_internal')
    for d in (exe_dir, internal_dir):
        if os.path.isdir(d) and d not in dll_dirs:
            dll_dirs.append(d)

    # 1) 显式加入随包 DLL 目录，使其在 _ssl.pyd 加载时具有最高搜索优先级
    for d in dll_dirs:
        try:
            os.add_dll_directory(d)
        except (OSError, AttributeError):
            pass

    # 2) 把随包目录前置到 PATH，并剔除含同名 OpenSSL DLL 的第三方目录
    original_path = os.environ.get('PATH', '')
    kept = []
    for entry in original_path.split(os.pathsep):
        if not entry:
            continue
        # 跳过含 libcrypto/libssl 的非随包目录，避免被优先加载
        if entry not in dll_dirs and (
            os.path.exists(os.path.join(entry, 'libcrypto-3-x64.dll'))
            or os.path.exists(os.path.join(entry, 'libcrypto-1_1-x64.dll'))
        ):
            continue
        kept.append(entry)
    os.environ['PATH'] = os.pathsep.join(dll_dirs + kept)


_fix_dll_search_path()

# Now import and run the main application
from app.main import main

if __name__ == "__main__":
    main()
