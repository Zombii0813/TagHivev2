#!/usr/bin/env python3
"""
使用 PyInstaller 打包 Python 后端为独立可执行文件
"""

import os
import sys
import time
import shutil
import subprocess
from pathlib import Path


def _rmtree_with_retry(path: Path, retries: int = 5, delay: float = 1.0):
    """带重试的目录删除。

    Windows 上文件常被杀毒软件、Search 索引器或刚结束的进程瞬时占用，
    导致 shutil.rmtree 抛 PermissionError。此处重试若干次以提高稳健性。

    Args:
        path: 待删除目录。
        retries: 最大重试次数。
        delay: 每次重试间隔（秒）。
    """
    for attempt in range(1, retries + 1):
        try:
            shutil.rmtree(path)
            return
        except (PermissionError, OSError) as exc:
            if attempt == retries:
                print(f"ERROR: 无法删除目录 {path}: {exc}")
                print("请确认没有 taghive-sidecar.exe 进程在运行后重试。")
                raise
            print(f"删除 {path} 失败（第 {attempt} 次），{delay}s 后重试...")
            time.sleep(delay)


def get_project_root() -> Path:
    """获取项目根目录"""
    script_dir = Path(__file__).parent.resolve()
    return script_dir.parent


def find_openssl_dll_dir(src_python: Path) -> Path | None:
    """探测打包 Python 环境中 OpenSSL DLL 所在目录。

    背景：PyInstaller 的二进制依赖分析按系统 PATH 顺序搜索 OpenSSL DLL
    （libcrypto-3-x64.dll / libssl-3-x64.dll）。若机器上存在其它 Anaconda
    安装或 MSYS2(mingw64)，其目录排在 PATH 前面时会被优先选中，打进版本
    较旧、与 _ssl.pyd 不匹配的 DLL，导致生产环境启动崩溃：
        ImportError: DLL load failed while importing _ssl: 找不到指定的程序

    本函数借助打包所用解释器（uv 管理的 .venv，其 base 指向 conda 环境）
    定位正确的 DLL 目录，供调用方前置到 PATH。

    Args:
        src_python: src-python 目录路径，用于通过 uv run 调用解释器。

    Returns:
        含 libcrypto-3-x64.dll 的目录；未找到时返回 None。
    """
    # 在打包环境的解释器内解析候选目录（conda 环境位于 base_prefix\Library\bin）
    probe = (
        "import os, sys\n"
        "for d in [\n"
        "    os.path.join(sys.base_prefix, 'Library', 'bin'),\n"
        "    os.path.join(sys.prefix, 'Library', 'bin'),\n"
        "    os.path.join(sys.base_prefix, 'DLLs'),\n"
        "    os.path.join(sys.prefix, 'DLLs'),\n"
        "]:\n"
        "    if os.path.exists(os.path.join(d, 'libcrypto-3-x64.dll')):\n"
        "        print(d)\n"
        "        break\n"
    )
    try:
        result = subprocess.run(
            ["uv", "run", "--directory", str(src_python), "python", "-c", probe],
            cwd=src_python,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"WARNING: 探测 OpenSSL DLL 目录失败: {exc}")
        return None

    out = result.stdout.strip()
    if out and Path(out).exists():
        return Path(out)
    return None


def clean_previous_builds(dist_dir: Path, build_dir: Path):
    """清理之前的构建文件"""
    print("Cleaning previous builds...")
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    if build_dir.exists():
        shutil.rmtree(build_dir)


def build_sidecar():
    """构建 sidecar 可执行文件"""
    project_root = get_project_root()
    src_python = project_root / "src-python"
    src_tauri = project_root / "src-tauri"
    resources_dir = src_tauri / "resources"
    
    # 确保 resources 目录存在
    resources_dir.mkdir(exist_ok=True)
    
    # PyInstaller 输出目录
    dist_dir = src_python / "dist"
    build_dir = src_python / "build"
    
    # 清理之前的构建
    clean_previous_builds(dist_dir, build_dir)

    # 探测并前置 OpenSSL DLL 目录到 PATH，避免 PyInstaller 从系统 PATH 上其它
    # Anaconda / mingw64 目录抓到不匹配的旧版 libcrypto/libssl，导致 _ssl 加载失败
    build_env = os.environ.copy()
    openssl_dir = find_openssl_dll_dir(src_python)
    expected_dll_size = None
    if openssl_dir is not None:
        print(f"Found OpenSSL DLL dir: {openssl_dir}")
        build_env["PATH"] = f"{openssl_dir}{os.pathsep}{build_env.get('PATH', '')}"
        libcrypto = openssl_dir / "libcrypto-3-x64.dll"
        if libcrypto.exists():
            expected_dll_size = libcrypto.stat().st_size
    else:
        print("WARNING: 未找到 OpenSSL DLL 目录，使用现有 PATH 继续打包")

    # 构建命令 - 使用 sidecar_entry.py 作为入口
    # 通过 uv run 调用 pyinstaller，确保使用 src-python/.venv 中的依赖
    cmd = [
        "uv", "run", "--directory", str(src_python),
        "pyinstaller",
        "--name", "taghive-sidecar",
        "--onedir",   # 目录模式：启动更快，无需每次解压到临时目录
        "--noconsole",  # 隐藏控制台窗口（生产环境）
        "--clean",
        "--noconfirm",
        # 添加 Python 路径
        "--paths", str(src_python),
        # 添加数据文件
        "--add-data", f"{src_python / 'app'};app",
        # 隐藏导入
        "--hidden-import", "app.api",
        "--hidden-import", "app.api.routes",
        "--hidden-import", "app.api.models",
        "--hidden-import", "app.api.thumbnails",
        "--hidden-import", "app.api.websocket",
        "--hidden-import", "app.core",
        "--hidden-import", "app.core.indexer",
        "--hidden-import", "app.core.search",
        "--hidden-import", "app.core.tag_manager",
        "--hidden-import", "app.core.cache",
        "--hidden-import", "app.db",
        "--hidden-import", "app.db.models",
        "--hidden-import", "app.db.session",
        "--hidden-import", "app.db.repo",
        "--hidden-import", "app.services",
        "--hidden-import", "app.services.scan_service",
        "--hidden-import", "app.services.thumbnail_service",
        "--hidden-import", "app.services.watch_service",
        "--hidden-import", "app.utils",
        "--hidden-import", "app.utils.file_types",
        "--hidden-import", "app.utils.hashing",
        "--hidden-import", "uvicorn",
        "--hidden-import", "fastapi",
        "--hidden-import", "socketio",
        "--hidden-import", "sqlalchemy",
        "--hidden-import", "watchdog",
        "--hidden-import", "PIL",
        # 工作目录
        "--workpath", str(build_dir),
        "--distpath", str(dist_dir),
        # 入口文件 - 使用 sidecar_entry.py
        str(src_python / "sidecar_entry.py"),
    ]
    
    print(f"Running: {' '.join(cmd)}")
    print(f"Working directory: {src_python}")
    
    # 运行 PyInstaller（使用前置了 OpenSSL DLL 目录的环境）
    result = subprocess.run(cmd, cwd=src_python, capture_output=False, env=build_env)

    if result.returncode != 0:
        print("ERROR: PyInstaller build failed!")
        sys.exit(1)

    # 校验打包进的 OpenSSL DLL 是否与打包环境一致，防止抓到错误版本
    bundled_dll = dist_dir / "taghive-sidecar" / "_internal" / "libcrypto-3-x64.dll"
    if expected_dll_size is not None and bundled_dll.exists():
        actual_size = bundled_dll.stat().st_size
        if actual_size != expected_dll_size:
            print(
                f"ERROR: 打包进的 libcrypto-3-x64.dll ({actual_size} 字节) "
                f"与打包环境 ({expected_dll_size} 字节) 不一致！"
            )
            print("可能仍从其它 PATH 目录抓到了错误版本的 OpenSSL DLL，已中止。")
            sys.exit(1)
        print(f"OpenSSL DLL 校验通过: {actual_size} 字节")

    # 复制生成的目录到 resources 目录（onedir 模式输出整个目录）
    source_dir = dist_dir / "taghive-sidecar"
    target_dir = resources_dir / "taghive-sidecar"

    if not source_dir.exists():
        print(f"ERROR: Expected sidecar directory not found: {source_dir}")
        sys.exit(1)

    # 清理旧的目标目录（Windows 上文件可能被杀毒/索引器瞬时占用，加重试）
    if target_dir.exists():
        _rmtree_with_retry(target_dir)

    print(f"Copying {source_dir} -> {target_dir}")
    shutil.copytree(source_dir, target_dir)

    # 计算目录总大小
    total_size = sum(f.stat().st_size for f in target_dir.rglob("*") if f.is_file())
    exe_name = "taghive-sidecar.exe" if sys.platform == "win32" else "taghive-sidecar"

    print(f"\n[OK] Sidecar built successfully! (onedir mode)")
    print(f"   Location: {target_dir}")
    print(f"   Total size: {total_size / 1024 / 1024:.1f} MB")
    print(f"   Executable: {target_dir / exe_name}")


if __name__ == "__main__":
    build_sidecar()
