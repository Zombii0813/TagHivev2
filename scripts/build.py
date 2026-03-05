#!/usr/bin/env python3
"""
TagHive 构建脚本
一键构建完整的应用程序
"""

import subprocess
import sys
import shutil
from pathlib import Path

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'

def log(msg, color=Colors.BLUE):
    print(f"{color}[TagHive Build]{Colors.END} {msg}")

def run_command(cmd, cwd=None, shell=False):
    """运行命令"""
    log(f"执行: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, cwd=cwd, shell=shell, capture_output=False)
    if result.returncode != 0:
        log(f"命令失败: {cmd}", Colors.RED)
        sys.exit(1)

def main():
    """主函数"""
    root_dir = Path(__file__).parent.parent
    
    log("开始构建 TagHive...", Colors.GREEN)
    
    # 1. 检查依赖
    log("检查依赖...")
    
    # 2. 构建前端
    log("构建前端...")
    ui_dir = root_dir / "src-ui"
    run_command(["npm", "install"], cwd=ui_dir, shell=True)
    run_command(["npm", "run", "build"], cwd=ui_dir, shell=True)
    
    # 3. 构建 Tauri 应用
    log("构建 Tauri 应用...")
    tauri_dir = root_dir / "src-tauri"
    
    if sys.platform == "win32":
        run_command(["cargo", "tauri", "build"], cwd=tauri_dir)
    else:
        run_command(["cargo", "tauri", "build"], cwd=tauri_dir)
    
    # 4. 输出结果
    log("构建完成！", Colors.GREEN)
    
    bundle_dir = tauri_dir / "target" / "release" / "bundle"
    if bundle_dir.exists():
        log(f"安装包位置: {bundle_dir}")
        
        # 列出构建产物
        for item in bundle_dir.rglob("*"):
            if item.is_file():
                size = item.stat().st_size / (1024 * 1024)  # MB
                log(f"  - {item.name} ({size:.1f} MB)")
    
    log("构建成功！", Colors.GREEN)

if __name__ == "__main__":
    main()
