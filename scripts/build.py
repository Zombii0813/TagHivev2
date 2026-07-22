#!/usr/bin/env python3
"""TagHive 一键生产构建脚本。

完整流程按以下顺序执行，任一步失败即中止：

  1. 环境检查      —— 确认 uv / npm / cargo / cargo-tauri 可用
  2. 打包 sidecar  —— 调用 build-sidecar.py，用 PyInstaller 把 Python 后端
                       打成独立目录，产物落到 src-tauri/resources/taghive-sidecar
  3. 前端依赖      —— npm install（幂等；缺 node_modules 或指定 --npm-install 时）
  4. 构建 Tauri    —— cargo tauri build，其 beforeBuildCommand 会自动跑
                       `npm run build` 构建前端，最终打出 NSIS 安装包
  5. 汇总产物      —— 列出 bundle 目录下的安装包及体积

用法：
    uv run --directory src-python python scripts/build.py [选项]

    # 或在已激活的 Python 环境中直接：
    python scripts/build.py

选项：
    --skip-sidecar     跳过 sidecar 打包（复用已有 resources/taghive-sidecar）
    --npm-install      强制执行 npm install（默认仅在缺 node_modules 时执行）
    --skip-tauri       只打 sidecar、不跑 cargo tauri build（用于调试）
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

# Windows 控制台默认 GBK 编码，直接输出脚本中的中文/ANSI 会乱码。
# 将标准输出/错误重配为 UTF-8，保证日志可读。
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


class Colors:
    """终端 ANSI 颜色常量。"""

    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    END = "\033[0m"


def log(msg: str, color: str = Colors.BLUE) -> None:
    """打印带统一前缀的日志。

    Args:
        msg: 日志内容。
        color: ANSI 颜色码，默认蓝色。
    """
    print(f"{color}[TagHive Build]{Colors.END} {msg}", flush=True)


def get_project_root() -> Path:
    """获取项目根目录（脚本所在目录的上一级）。

    Returns:
        项目根目录的绝对路径。
    """
    return Path(__file__).parent.resolve().parent


def run_command(cmd: list[str], cwd: Path | None = None, shell: bool = False) -> None:
    """运行外部命令，失败即退出。

    Args:
        cmd: 命令及参数列表。
        cwd: 工作目录。
        shell: 是否通过 shell 执行（Windows 上跑 npm 需要）。
    """
    printable = " ".join(cmd) if isinstance(cmd, list) else cmd
    log(f"执行: {printable}")
    result = subprocess.run(cmd, cwd=cwd, shell=shell)
    if result.returncode != 0:
        log(f"命令失败（退出码 {result.returncode}）: {printable}", Colors.RED)
        sys.exit(1)


def check_tool(name: str, args: list[str], hint: str) -> bool:
    """检查某个命令行工具是否可用。

    Windows 上 npm 等工具是 .cmd 批处理，非 shell 方式无法直接执行，故统一
    通过 shell 探测（Windows），其余平台保持列表参数直接调用。

    Args:
        name: 工具展示名。
        args: 用于探测的命令（如 ["uv", "--version"]）。
        hint: 未找到时给用户的安装提示。

    Returns:
        可用返回 True，否则 False。
    """
    use_shell = sys.platform == "win32"
    cmd = " ".join(args) if use_shell else args
    try:
        subprocess.run(cmd, capture_output=True, check=True, shell=use_shell)
    except (subprocess.CalledProcessError, OSError):
        log(f"{name} 探测失败：`{' '.join(args)}` 未正常返回。{hint}", Colors.RED)
        return False
    log(f"  [OK] {name}", Colors.GREEN)
    return True


def check_environment() -> None:
    """检查生产构建所需的全部工具链，缺任一项即中止。"""
    log("检查构建环境...")
    ok = True
    ok &= check_tool("uv", ["uv", "--version"], "安装参见 https://docs.astral.sh/uv/")
    ok &= check_tool("npm", ["npm", "--version"], "请安装 Node.js（含 npm）。")
    ok &= check_tool("cargo", ["cargo", "--version"], "请安装 Rust 工具链（rustup）。")
    # cargo-tauri 是 cargo 子命令，单独探测
    ok &= check_tool(
        "cargo-tauri",
        ["cargo", "tauri", "--version"],
        "请执行 `cargo install tauri-cli --version ^2`。",
    )
    if not ok:
        log("环境检查未通过，已中止。", Colors.RED)
        sys.exit(1)


def build_sidecar(root_dir: Path) -> None:
    """打包 Python sidecar。

    复用同目录下的 build-sidecar.py（内部通过 uv run + PyInstaller 打包），
    保证与单独打 sidecar 时行为一致（含 OpenSSL DLL 校验）。

    Args:
        root_dir: 项目根目录。
    """
    log("打包 Python sidecar（PyInstaller）...", Colors.GREEN)
    sidecar_script = root_dir / "scripts" / "build-sidecar.py"
    src_python = root_dir / "src-python"
    # 用 uv run 保证使用 src-python/.venv 的解释器与依赖
    run_command(
        ["uv", "run", "--directory", str(src_python), "python", str(sidecar_script)],
        cwd=root_dir,
    )


def ensure_frontend_deps(root_dir: Path, force: bool) -> None:
    """确保前端依赖已安装。

    默认仅在缺 node_modules 时执行 npm install；前端本身的构建由
    cargo tauri build 的 beforeBuildCommand（npm run build）负责，此处不重复。

    Args:
        root_dir: 项目根目录。
        force: 为 True 时无条件执行 npm install。
    """
    ui_dir = root_dir / "src-ui"
    node_modules = ui_dir / "node_modules"
    if force or not node_modules.exists():
        log("安装前端依赖（npm install）...", Colors.GREEN)
        run_command(["npm", "install"], cwd=ui_dir, shell=True)
    else:
        log("前端依赖已存在，跳过 npm install（如需重装用 --npm-install）")


def build_tauri(root_dir: Path) -> None:
    """构建 Tauri 应用并打出安装包。

    cargo tauri build 会先执行 beforeBuildCommand（npm run build）构建前端，
    再编译 Rust 外壳并打包（当前 targets 配置为 NSIS）。

    Args:
        root_dir: 项目根目录。
    """
    log("构建 Tauri 应用（cargo tauri build）...", Colors.GREEN)
    run_command(["cargo", "tauri", "build"], cwd=root_dir / "src-tauri")


def report_artifacts(root_dir: Path) -> None:
    """列出构建产物（安装包）及其体积。

    Args:
        root_dir: 项目根目录。
    """
    bundle_dir = root_dir / "src-tauri" / "target" / "release" / "bundle"
    if not bundle_dir.exists():
        log("未找到 bundle 目录，可能 Tauri 打包未产出安装包。", Colors.YELLOW)
        return
    log(f"安装包位置: {bundle_dir}", Colors.GREEN)
    found = False
    for item in sorted(bundle_dir.rglob("*")):
        if item.is_file() and item.suffix.lower() in {".exe", ".msi"}:
            size = item.stat().st_size / (1024 * 1024)
            log(f"  - {item.relative_to(bundle_dir)} ({size:.1f} MB)")
            found = True
    if not found:
        log("bundle 目录下未发现 .exe/.msi 安装包。", Colors.YELLOW)


def main() -> None:
    """脚本入口：解析参数并按序执行完整生产构建流程。"""
    parser = argparse.ArgumentParser(description="TagHive 一键生产构建")
    parser.add_argument(
        "--skip-sidecar", action="store_true", help="跳过 sidecar 打包，复用已有产物"
    )
    parser.add_argument(
        "--npm-install", action="store_true", help="强制执行 npm install"
    )
    parser.add_argument(
        "--skip-tauri", action="store_true", help="只打 sidecar，不跑 cargo tauri build"
    )
    args = parser.parse_args()

    root_dir = get_project_root()
    start = time.monotonic()
    log("开始生产构建 TagHive...", Colors.GREEN)

    check_environment()

    if args.skip_sidecar:
        log("按参数跳过 sidecar 打包。", Colors.YELLOW)
    else:
        build_sidecar(root_dir)

    if args.skip_tauri:
        log("按参数跳过 Tauri 构建，流程结束。", Colors.YELLOW)
        return

    ensure_frontend_deps(root_dir, force=args.npm_install)
    build_tauri(root_dir)
    report_artifacts(root_dir)

    elapsed = time.monotonic() - start
    log(f"构建成功！耗时 {elapsed:.0f} 秒。", Colors.GREEN)


if __name__ == "__main__":
    main()
