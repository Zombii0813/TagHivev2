#!/usr/bin/env python3
"""
使用 PyInstaller 打包 Python 后端为独立可执行文件
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


def get_project_root() -> Path:
    """获取项目根目录"""
    script_dir = Path(__file__).parent.resolve()
    return script_dir.parent


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
    
    # 构建命令 - 使用 sidecar_entry.py 作为入口
    cmd = [
        "pyinstaller",
        "--name", "taghive-sidecar",
        "--onefile",  # 打包成单个文件
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
    
    # 运行 PyInstaller
    result = subprocess.run(cmd, cwd=src_python, capture_output=False)
    
    if result.returncode != 0:
        print("ERROR: PyInstaller build failed!")
        sys.exit(1)
    
    # 复制生成的可执行文件到 resources 目录
    exe_name = "taghive-sidecar.exe" if sys.platform == "win32" else "taghive-sidecar"
    source_exe = dist_dir / exe_name
    target_exe = resources_dir / exe_name
    
    if not source_exe.exists():
        print(f"ERROR: Expected executable not found: {source_exe}")
        sys.exit(1)
    
    print(f"Copying {source_exe} to {target_exe}")
    shutil.copy2(source_exe, target_exe)
    
    print(f"\n✅ Sidecar built successfully!")
    print(f"   Location: {target_exe}")
    print(f"   Size: {target_exe.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    build_sidecar()
