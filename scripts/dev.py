#!/usr/bin/env python3
"""
TagHive 开发启动脚本
一键启动 Python Sidecar 和前端开发服务器
"""

import subprocess
import sys
import time
import signal
import os
from pathlib import Path

# 颜色输出
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'

def log(msg, color=Colors.BLUE):
    print(f"{color}[TagHive Dev]{Colors.END} {msg}")

def main():
    """主函数"""
    # 获取项目根目录
    root_dir = Path(__file__).parent.parent
    
    # 启动进程列表
    processes = []
    
    def cleanup(signum=None, frame=None):
        """清理进程"""
        log("正在停止所有服务...", Colors.YELLOW)
        for p in processes:
            try:
                p.terminate()
                p.wait(timeout=5)
            except:
                p.kill()
        log("所有服务已停止", Colors.GREEN)
        sys.exit(0)
    
    # 注册信号处理
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    try:
        # 启动 Python Sidecar
        log("启动 Python Sidecar...")
        python_dir = root_dir / "src-python"
        
        # 检查虚拟环境
        if os.name == 'nt':  # Windows
            python_exe = python_dir / "venv" / "Scripts" / "python.exe"
        else:
            python_exe = python_dir / "venv" / "bin" / "python"
        
        if python_exe.exists():
            python_cmd = str(python_exe)
        else:
            python_cmd = sys.executable
        
        sidecar = subprocess.Popen(
            [python_cmd, "-m", "app.main"],
            cwd=python_dir,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        processes.append(sidecar)
        
        # 等待 Python 服务启动
        log("等待 Python 服务启动...")
        time.sleep(2)
        
        # 启动前端开发服务器
        log("启动前端开发服务器...")
        ui_dir = root_dir / "src-ui"
        
        frontend = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=ui_dir,
            shell=True if os.name == 'nt' else False
        )
        processes.append(frontend)
        
        log("所有服务已启动！", Colors.GREEN)
        log("- Python Sidecar: http://127.0.0.1:8721")
        log("- 前端开发服务器: http://localhost:5173")
        log("按 Ctrl+C 停止所有服务")
        
        # 等待进程
        for p in processes:
            p.wait()
            
    except Exception as e:
        log(f"错误: {e}", Colors.RED)
        cleanup()

if __name__ == "__main__":
    main()
