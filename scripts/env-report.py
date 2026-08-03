#!/usr/bin/env python3
"""TagHive 开发环境体检脚本。

用于在多台开发机之间定位 ``cargo tauri dev`` 行为差异的根因。脚本只读取信息，
不修改任何项目文件或系统配置，可跨平台运行（Windows / macOS / Linux），
仅依赖 Python 标准库。

采集内容按「最容易造成机器间差异」排序：

1. 主机与区域设置（OS 版本、代码页、编码、DPI 缩放、时区）
2. 工具链版本（rustc / cargo / tauri-cli / node / npm / python / uv / git）
3. WebView2 运行时版本（Windows 渲染差异的首要来源）
4. 未纳入 Git 的本地配置（``src-tauri/config.json``、``.env``、``.taghive``）
5. Python 解释器解析结果（复刻 ``sidecar.rs`` 的四级回退逻辑）
6. 依赖锁定状态（Cargo.lock / package-lock.json / uv.lock 指纹与关键包实际版本）
7. Python 运行时探针（sqlite / FTS5 / PyAV / pymediainfo 等）
8. PATH 分析（conda、MSYS2 抢占 OpenSSL / MediaInfo DLL）
9. 端口占用与数据目录现状
10. Git 工作区状态（含 core.autocrlf 等会改变文件内容的配置）

用法::

    python scripts/env-report.py                       # 打印报告并保存 JSON
    python scripts/env-report.py --no-save             # 只打印，不落盘
    python scripts/env-report.py --json out.json       # 指定 JSON 输出路径
    python scripts/env-report.py --compare a.json b.json   # 对比两台机器的报告
    python scripts/env-report.py --compare a.json b.json --all  # 连相同项一起列出

典型排查流程：在每台机器上执行一次，把生成的
``.taghive/env-report-<hostname>.json`` 收集到一处，再用 ``--compare`` 直接看差异。
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import locale
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

IS_WINDOWS = os.name == "nt"

# 报告结构版本；字段含义发生不兼容变化时递增，便于 --compare 时提示
REPORT_SCHEMA_VERSION = 1

# 前端关注的关键包（node_modules 中的实际安装版本）
UI_KEY_PACKAGES = [
    "vue",
    "vite",
    "@vitejs/plugin-vue",
    "vue-tsc",
    "typescript",
    "element-plus",
    "pinia",
    "vue-router",
    "axios",
    "socket.io-client",
    "vue-virtual-scroller",
    "tailwindcss",
    "postcss",
    "autoprefixer",
    "@tauri-apps/api",
    "@tauri-apps/cli",
    "@tauri-apps/plugin-dialog",
    "@tauri-apps/plugin-fs",
    "@tauri-apps/plugin-shell",
]

# Rust 侧关注的 crate（决定窗口 / WebView 行为）
CARGO_KEY_CRATES = [
    "tauri",
    "tauri-build",
    "tauri-runtime",
    "tauri-runtime-wry",
    "tauri-plugin-shell",
    "tauri-plugin-dialog",
    "tauri-plugin-fs",
    "wry",
    "tao",
    "webview2-com",
    "webview2-com-sys",
    "windows",
    "tokio",
    "serde",
]

# Python 侧关注的包
PY_KEY_PACKAGES = [
    "fastapi",
    "uvicorn",
    "python-socketio",
    "python-engineio",
    "sqlalchemy",
    "watchdog",
    "pillow",
    "pydantic",
    "pydantic-settings",
    "httpx",
    "pymediainfo",
    "av",
    "pyinstaller",
    "pytest",
]

# 需要完整记录的环境变量前缀（值可能影响构建 / 运行行为）
ENV_PREFIXES = (
    "TAGHIVE_",
    "TAURI_",
    "RUST",
    "CARGO",
    "NODE",
    "NPM_",
    "npm_config_",
    "PYTHON",
    "UV_",
    "VIRTUAL_ENV",
    "CONDA",
    "WEBVIEW2_",
    "VITE_",
)

# 单独列出的环境变量（不按前缀匹配）
ENV_EXACT = (
    "LANG",
    "LC_ALL",
    "TZ",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "PYTHONUTF8",
    "PYTHONIOENCODING",
    "TERM",
    "WSL_DISTRO_NAME",
    "MSYSTEM",
    "SHELL",
    "COMSPEC",
    "PROCESSOR_ARCHITECTURE",
)

# PATH 上会抢占动态库的可疑目录关键词（参见 scripts/build-sidecar.py 的 OpenSSL 说明）
SUSPICIOUS_PATH_KEYWORDS = (
    "anaconda",
    "miniconda",
    "conda",
    "msys",
    "mingw",
    "cygwin",
    "chocolatey",
    "scoop",
    "strawberry",
    "cmder",
)

# 在 PATH 上探测是否存在多份、版本可能冲突的动态库
SHADOWED_LIBS = (
    "libcrypto-3-x64.dll",
    "libssl-3-x64.dll",
    "MediaInfo.dll",
    "avcodec-60.dll",
    "avformat-60.dll",
    "ffmpeg.exe",
    "ffprobe.exe",
)

# --compare 时默认忽略的字段（易变且无诊断价值）
VOLATILE_KEYS = (
    "report.generated_at",
    "report.generated_utc",
    "report.elapsed_seconds",
    "host.hostname",
    "host.username",
    "python_runtime.probe_stderr_tail",
)

# 结尾匹配即视为易变字段
VOLATILE_SUFFIXES = (".mtime", ".size_bytes", ".entries", ".pid")

# 含有这些片段的字段视为易变（各机数据量本就不同，无诊断价值）
VOLATILE_SUBSTRINGS = (".row_counts.", ".log_files.")


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #


def run(cmd: list[str], timeout: int = 30, cwd: Path | None = None) -> str | None:
    """执行外部命令并返回合并后的输出。

    Args:
        cmd: 命令与参数列表；``cmd[0]`` 会先经 ``shutil.which`` 解析，
            Windows 下可正确命中 ``.cmd`` / ``.bat`` 包装脚本。
        timeout: 超时秒数，超时视为失败。
        cwd: 执行目录，默认继承当前进程。

    Returns:
        命令输出（stdout + stderr，已 strip）；命令不存在返回 ``None``，
        执行异常返回以 ``<error:`` 开头的字符串。
    """
    exe = shutil.which(cmd[0], path=os.environ.get("PATH"))
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, *cmd[1:]],
            capture_output=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return f"<error: timeout after {timeout}s>"
    except OSError as exc:
        return f"<error: {exc}>"
    out = f"{proc.stdout or ''}{proc.stderr or ''}".strip()
    return out or f"<exit {proc.returncode}, no output>"


def first_line(text: str | None) -> str | None:
    """取多行输出的首行，便于版本号展示。

    Args:
        text: 原始文本，可为 ``None``。

    Returns:
        首个非空行；输入为空时返回 ``None``。
    """
    if not text:
        return text
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return None


def file_digest(path: Path, length: int = 12) -> str | None:
    """计算文件 SHA256 的短摘要，用于比对锁文件是否一致。

    Args:
        path: 目标文件。
        length: 摘要保留的十六进制字符数。

    Returns:
        短摘要字符串；文件不存在或读取失败返回 ``None``。
    """
    try:
        h = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
    return h[:length]


def describe_path(path: Path, *, digest: bool = False) -> dict[str, Any]:
    """描述一个路径的存在性与基本属性。

    Args:
        path: 目标路径。
        digest: 为文件时是否附带内容摘要。

    Returns:
        含 ``exists`` / ``path`` 等键的字典；文件另含大小、修改时间，
        目录另含直接子项数量。
    """
    info: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return info
    try:
        st = path.stat()
    except OSError as exc:
        info["error"] = str(exc)
        return info
    info["mtime"] = datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
    if path.is_dir():
        info["type"] = "dir"
        try:
            info["entries"] = len(list(path.iterdir()))
        except OSError:
            info["entries"] = "<unreadable>"
    else:
        info["type"] = "file"
        info["size_bytes"] = st.st_size
        if digest:
            info["sha256_12"] = file_digest(path)
    return info


def read_json(path: Path) -> Any:
    """读取 JSON 文件，失败时返回错误描述而非抛出异常。

    Args:
        path: JSON 文件路径。

    Returns:
        解析后的对象；文件不存在返回 ``None``，解析失败返回错误字符串。
    """
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"<error: {exc}>"


def port_state(port: int, host: str = "127.0.0.1") -> str:
    """探测本机端口是否已被监听。

    Args:
        port: 端口号。
        host: 探测地址，默认回环地址。

    Returns:
        ``"in_use"`` 或 ``"free"``；异常时返回错误描述。
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.35)
            return "in_use" if sock.connect_ex((host, port)) == 0 else "free"
    except OSError as exc:
        return f"<error: {exc}>"


def project_root() -> Path:
    """定位项目根目录（脚本所在 ``scripts/`` 的上一级）。

    Returns:
        项目根目录的绝对路径。
    """
    return Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# 各采集模块
# --------------------------------------------------------------------------- #


def _locale_encoding() -> str:
    """获取当前 locale 编码，兼容 Python 3.11 之前的版本。

    Returns:
        编码名称字符串。
    """
    getter = getattr(locale, "getencoding", None)
    if callable(getter):
        return str(getter())
    return locale.getpreferredencoding(False)


def collect_host() -> dict[str, Any]:
    """采集主机、OS、区域设置与显示相关信息。

    Windows 下额外读取 ACP/OEMCP 代码页、长路径开关与 DPI 缩放，这些是
    中文乱码与界面尺寸差异的常见来源。

    Returns:
        主机信息字典。
    """
    info: dict[str, Any] = {
        "hostname": platform.node(),
        "username": os.environ.get("USERNAME") or os.environ.get("USER") or "<unknown>",
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "<unknown>",
        "cpu_count_logical": os.cpu_count(),
        "python_arch": platform.architecture()[0],
        "timezone": "/".join(time.tzname) if time.tzname else "<unknown>",
        "utc_offset_hours": round(-time.timezone / 3600, 2),
        "preferred_encoding": locale.getpreferredencoding(False),
        "filesystem_encoding": sys.getfilesystemencoding(),
        "stdout_encoding": getattr(sys.stdout, "encoding", None),
        "locale_encoding": _locale_encoding(),
        "locale_setting": "|".join(str(x) for x in locale.getlocale()),
    }

    if IS_WINDOWS:
        info.update(_collect_windows_host())
    else:
        info["uname"] = " ".join(platform.uname())
        os_release = Path("/etc/os-release")
        if os_release.exists():
            info["os_release"] = first_line(
                next(
                    (
                        line
                        for line in os_release.read_text(encoding="utf-8", errors="replace").splitlines()
                        if line.startswith("PRETTY_NAME=")
                    ),
                    "",
                ).partition("=")[2].strip('"')
            )
        if platform.system() == "Linux":
            info["display_server"] = (
                os.environ.get("XDG_SESSION_TYPE")
                or ("wayland" if os.environ.get("WAYLAND_DISPLAY") else None)
                or ("x11" if os.environ.get("DISPLAY") else None)
                or "<unknown>"
            )
            info["gtk_scale"] = os.environ.get("GDK_SCALE", "<unset>")
    return info


def _collect_windows_host() -> dict[str, Any]:
    """采集 Windows 专属主机信息。

    Returns:
        含代码页、长路径开关、构建号与 DPI 缩放的字典。
    """
    info: dict[str, Any] = {}

    # 代码页：ACP=65001 表示开启了「使用 Unicode UTF-8 提供全球语言支持」
    nls = _reg_values(
        r"SYSTEM\CurrentControlSet\Control\Nls\CodePage", ("ACP", "OEMCP", "MACCP"), hive="HKLM"
    )
    info["windows_code_page"] = nls
    info["windows_utf8_beta_enabled"] = nls.get("ACP") == "65001"

    # chcp 的提示文本本身按 OEM 代码页编码，这里只取数字避免乱码
    chcp = run(["chcp"], timeout=10) or ""
    m = re.search(r"(\d{3,5})", chcp)
    info["console_chcp"] = m.group(1) if m else "<unknown>"

    long_paths = _reg_values(
        r"SYSTEM\CurrentControlSet\Control\FileSystem", ("LongPathsEnabled",), hive="HKLM"
    )
    info["long_paths_enabled"] = long_paths.get("LongPathsEnabled", "<unset>")

    build = _reg_values(
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        ("DisplayVersion", "ReleaseId", "CurrentBuild", "UBR", "ProductName", "EditionID"),
        hive="HKLM",
    )
    info["windows_build_info"] = build

    dev_mode = _reg_values(
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock",
        ("AllowDevelopmentWithoutDevLicense",),
        hive="HKLM",
    )
    info["developer_mode"] = dev_mode.get("AllowDevelopmentWithoutDevLicense", "<unset>")

    info.update(_windows_display_info())
    return info


def _windows_display_info() -> dict[str, Any]:
    """读取 Windows 主显示器分辨率与 DPI 缩放。

    DPI 缩放不同会直接改变 WebView 的 CSS 像素布局，是「同一份代码界面观感不同」
    的高频原因。

    Returns:
        含分辨率与缩放比例的字典；调用失败时给出错误说明。
    """
    out: dict[str, Any] = {}
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        try:
            # 使用 per-monitor v2 感知，读到的是物理像素
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            try:
                user32.SetProcessDPIAware()
            except Exception:  # noqa: BLE001 - 探测性调用，失败不影响后续
                pass
        out["screen_pixels"] = f"{user32.GetSystemMetrics(0)}x{user32.GetSystemMetrics(1)}"
        out["virtual_screen_pixels"] = f"{user32.GetSystemMetrics(78)}x{user32.GetSystemMetrics(79)}"
        out["monitor_count"] = user32.GetSystemMetrics(80)
        try:
            dpi = int(user32.GetDpiForSystem())
            out["system_dpi"] = dpi
            out["display_scale"] = f"{round(dpi / 96 * 100)}%"
        except AttributeError:
            out["system_dpi"] = "<unavailable>"
    except Exception as exc:  # noqa: BLE001 - ctypes 调用受系统策略影响
        out["display_probe_error"] = str(exc)
    return out


def _reg_values(subkey: str, names: Iterable[str], hive: str = "HKLM") -> dict[str, str]:
    """批量读取注册表值（仅 Windows，只读）。

    Args:
        subkey: 相对于 hive 的子键路径。
        names: 需要读取的值名称。
        hive: ``"HKLM"`` 或 ``"HKCU"``。

    Returns:
        名称到字符串值的映射；缺失的值不出现在结果中。
    """
    if not IS_WINDOWS:
        return {}
    import winreg  # 延迟导入，非 Windows 平台不可用

    root = winreg.HKEY_LOCAL_MACHINE if hive == "HKLM" else winreg.HKEY_CURRENT_USER
    result: dict[str, str] = {}
    for access in (winreg.KEY_READ, winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(root, subkey, 0, access) as key:
                for name in names:
                    if name in result:
                        continue
                    try:
                        result[name] = str(winreg.QueryValueEx(key, name)[0])
                    except FileNotFoundError:
                        continue
        except OSError:
            continue
    return result


def collect_webview() -> dict[str, Any]:
    """采集 WebView / 渲染引擎信息。

    Windows 上 Tauri 使用系统 WebView2 Runtime，其版本随 Edge 自动更新，
    是两台机器渲染差异（CSS 支持、字体回退、滚动行为）最直接的变量。

    Returns:
        WebView 相关信息字典。
    """
    info: dict[str, Any] = {}
    if IS_WINDOWS:
        # WebView2 Evergreen Runtime 的固定 GUID
        guid = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        for hive in ("HKLM", "HKCU"):
            for base in (
                rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}",
                rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}",
            ):
                vals = _reg_values(base, ("pv", "name"), hive=hive)
                if vals.get("pv"):
                    info["webview2_runtime_version"] = vals["pv"]
                    info["webview2_registry_hive"] = hive
                    break
            if "webview2_runtime_version" in info:
                break
        info.setdefault("webview2_runtime_version", "<not found>")

        edge = _reg_values(
            r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"
            r"\{56EB18F8-B008-4CBD-B6D2-8C97FE7E9062}",
            ("pv",),
            hive="HKLM",
        )
        info["edge_stable_version"] = edge.get("pv", "<not found>")

        # 项目显式指定的 WebView 数据目录（便携模式）
        info["project_webview_data_dir"] = describe_path(project_root() / ".taghive" / "webview")
    elif platform.system() == "Darwin":
        info["webview"] = "WKWebView (随系统 Safari 版本)"
        info["safari_version"] = first_line(
            run(["defaults", "read", "/Applications/Safari.app/Contents/Info.plist", "CFBundleShortVersionString"])
            or ""
        ) or "<unknown>"
    else:
        info["webview"] = "WebKitGTK"
        pkg = run(["pkg-config", "--modversion", "webkit2gtk-4.1"]) or run(
            ["pkg-config", "--modversion", "webkit2gtk-4.0"]
        )
        info["webkit2gtk_version"] = first_line(pkg) or "<not found>"
    return info


def collect_toolchain() -> dict[str, Any]:
    """采集构建工具链版本与安装位置。

    Returns:
        工具名到版本 / 路径信息的字典；未安装的工具标记为 ``<not found>``。
    """
    tools: dict[str, Any] = {}

    def probe(key: str, cmd: list[str], *, full: bool = False) -> None:
        """探测单个命令的版本与解析路径。"""
        out = run(cmd)
        tools[key] = {
            "resolved": shutil.which(cmd[0]) or "<not found>",
            "version": (out if full else first_line(out)) if out else "<not found>",
        }

    probe("rustc", ["rustc", "-vV"], full=True)
    probe("cargo", ["cargo", "--version"])
    probe("rustup_default", ["rustup", "show", "active-toolchain"])
    probe("cargo_tauri", ["cargo", "tauri", "--version"])
    probe("node", ["node", "--version"])
    probe("npm", ["npm", "--version"])
    probe("pnpm", ["pnpm", "--version"])
    probe("python", ["python", "--version"])
    probe("python3", ["python3", "--version"])
    probe("uv", ["uv", "--version"])
    probe("git", ["git", "--version"])
    if IS_WINDOWS:
        probe("msvc_link", ["link", "/?"])
        tools["msvc_link"]["version"] = first_line(tools["msvc_link"]["version"] or "")

    tools["running_python"] = {
        "executable": sys.executable,
        "version": sys.version.replace("\n", " "),
    }

    # rustup 工具链清单：多工具链共存时容易出现「本机默认不同」
    toolchains = run(["rustup", "toolchain", "list"])
    if toolchains:
        tools["rustup_toolchains"] = [line.strip() for line in toolchains.splitlines() if line.strip()]

    # Cargo 全局配置会影响 target-dir、linker、镜像源
    cargo_home = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo"))
    cargo_cfg = next(
        (p for p in (cargo_home / "config.toml", cargo_home / "config") if p.exists()),
        None,
    )
    tools["cargo_home"] = str(cargo_home)
    tools["cargo_global_config"] = (
        {"path": str(cargo_cfg), "sha256_12": file_digest(cargo_cfg), "content": _read_text_capped(cargo_cfg)}
        if cargo_cfg
        else "<none>"
    )

    npmrc_files = [Path.home() / ".npmrc", project_root() / "src-ui" / ".npmrc"]
    tools["npmrc"] = {
        str(p): (_read_text_capped(p) if p.exists() else "<none>") for p in npmrc_files
    }
    return tools


def _read_text_capped(path: Path | None, limit: int = 2000) -> str | None:
    """读取文本文件，超出上限时截断。

    Args:
        path: 文件路径，可为 ``None``。
        limit: 最大字符数。

    Returns:
        文件内容（可能被截断）；路径无效返回 ``None``。
    """
    if not path or not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"<error: {exc}>"
    return text if len(text) <= limit else f"{text[:limit]}\n<...truncated...>"


def collect_local_config(root: Path) -> dict[str, Any]:
    """采集未纳入 Git 的本地配置文件。

    ``.gitignore`` 忽略了 ``config.json`` 与 ``.env``，它们在不同机器上取值不同，
    却直接决定 sidecar 用哪个 Python、数据写到哪里 —— 这是本项目最典型的
    「同代码不同表现」来源。

    Args:
        root: 项目根目录。

    Returns:
        本地配置信息字典。
    """
    info: dict[str, Any] = {}

    tauri_cfg_path = root / "src-tauri" / "config.json"
    info["src_tauri_config_json"] = describe_path(tauri_cfg_path, digest=True)
    if tauri_cfg_path.exists():
        info["src_tauri_config_json"]["content"] = read_json(tauri_cfg_path)

    for rel in (
        "src-python/.env",
        "src-python/.env.local",
        "src-ui/.env",
        "src-ui/.env.local",
        "src-ui/.env.development",
        ".env",
    ):
        p = root / rel
        entry = describe_path(p, digest=True)
        if p.exists():
            # .env 可能含敏感值，只记录键名
            entry["keys"] = _env_file_keys(p)
        info[rel] = entry

    info["dot_taghive"] = {
        "root": describe_path(root / ".taghive"),
        "data": describe_path(root / ".taghive" / "data"),
        "logs": describe_path(root / ".taghive" / "logs"),
        "webview": describe_path(root / ".taghive" / "webview"),
    }

    bundled = root / "src-tauri" / "resources"
    info["src_tauri_resources"] = describe_path(bundled)
    if bundled.exists():
        try:
            info["src_tauri_resources_entries"] = sorted(p.name for p in bundled.iterdir())
        except OSError:
            pass

    info["src_tauri_target_debug"] = describe_path(root / "src-tauri" / "target" / "debug")
    info["ui_node_modules"] = describe_path(root / "src-ui" / "node_modules")
    info["py_venv"] = describe_path(root / "src-python" / ".venv")
    return info


def _env_file_keys(path: Path) -> list[str]:
    """提取 .env 文件的键名（不读取值，避免泄露凭据）。

    Args:
        path: .env 文件路径。

    Returns:
        键名列表。
    """
    keys: list[str] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            keys.append(line.split("=", 1)[0].strip())
    except OSError:
        return ["<unreadable>"]
    return keys


def collect_python_resolution(root: Path) -> dict[str, Any]:
    """复刻 ``src-tauri/src/sidecar.rs`` 的开发模式 Python 解析顺序。

    优先级：``TAGHIVE_PYTHON_PATH`` 环境变量 → ``src-tauri/config.json`` →
    ``src-python/.venv`` → 系统 ``python`` / ``python3``。任意一级在两台机器上
    命中不同，都会导致 sidecar 依赖版本不同。

    Args:
        root: 项目根目录。

    Returns:
        含候选清单与最终选中项的字典。
    """
    src_python = root / "src-python"
    candidates: list[dict[str, Any]] = []
    chosen: dict[str, Any] | None = None

    env_path = os.environ.get("TAGHIVE_PYTHON_PATH")
    if env_path:
        p = Path(env_path)
        entry = {"source": "env:TAGHIVE_PYTHON_PATH", "path": str(p), "exists": p.exists()}
        candidates.append(entry)
        if p.exists():
            chosen = entry

    cfg = read_json(root / "src-tauri" / "config.json")
    if isinstance(cfg, dict):
        raw = str((cfg.get("python") or {}).get("path", ""))
        if raw:
            p = _expand_tilde(raw)
            entry = {
                "source": "src-tauri/config.json",
                "declared": raw,
                "path": str(p),
                "exists": p.exists(),
                "env_type": (cfg.get("python") or {}).get("type"),
            }
            candidates.append(entry)
            if chosen is None and p.exists():
                chosen = entry
        if cfg.get("data_dir"):
            candidates.append(
                {"source": "src-tauri/config.json:data_dir", "declared": cfg["data_dir"]}
            )

    venv_python = src_python / (".venv/Scripts/python.exe" if IS_WINDOWS else ".venv/bin/python")
    entry = {"source": "src-python/.venv", "path": str(venv_python), "exists": venv_python.exists()}
    candidates.append(entry)
    if chosen is None and venv_python.exists():
        chosen = entry

    sys_name = "python" if IS_WINDOWS else "python3"
    resolved_sys = shutil.which(sys_name)
    entry = {
        "source": f"system:{sys_name}",
        "path": resolved_sys or "<not found>",
        "exists": bool(resolved_sys),
    }
    candidates.append(entry)
    if chosen is None:
        chosen = entry

    return {
        "candidates": candidates,
        "effective_source": chosen.get("source") if chosen else None,
        "effective_python": chosen.get("path") if chosen else None,
        "working_dir": str(src_python),
        "note": "与 sidecar.rs::get_sidecar_path(debug) 的回退顺序一致",
    }


def _expand_tilde(raw: str) -> Path:
    """按 Rust 端逻辑展开路径中的 ``~``。

    Args:
        raw: 原始路径字符串。

    Returns:
        展开后的路径对象。
    """
    if raw.startswith("~/") or raw.startswith("~\\"):
        return Path.home() / raw[2:]
    return Path(raw)


def collect_python_runtime(python_exe: str | None, root: Path) -> dict[str, Any]:
    """在实际使用的解释器中运行探针，采集运行时能力与包版本。

    重点关注 SQLite 版本与 FTS5 可用性（``files_fts`` 依赖）、PyAV 携带的
    FFmpeg 库版本（决定 ts 等格式能否播放）、pymediainfo 的 MediaInfo 库。

    Args:
        python_exe: 解释器路径；``None`` 或不存在时退化为当前解释器。
        root: 项目根目录，作为探针的工作目录基准。

    Returns:
        探针结果字典。
    """
    probe = r'''
import json, os, sys, sqlite3, platform

out = {}
out["executable"] = sys.executable
out["version"] = sys.version.replace("\n", " ")
out["implementation"] = platform.python_implementation()
out["arch"] = platform.architecture()[0]
out["prefix"] = sys.prefix
out["base_prefix"] = sys.base_prefix
out["in_venv"] = sys.prefix != sys.base_prefix
out["filesystem_encoding"] = sys.getfilesystemencoding()
out["stdout_encoding"] = getattr(sys.stdout, "encoding", None)
out["utf8_mode"] = getattr(sys.flags, "utf8_mode", None)
out["sqlite_runtime_version"] = sqlite3.sqlite_version
out["sqlite_threadsafety"] = getattr(sqlite3, "threadsafety", None)

try:
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE VIRTUAL TABLE _probe_fts USING fts5(x)")
        out["sqlite_fts5"] = True
    except Exception as exc:
        out["sqlite_fts5"] = "unavailable: %s" % exc
    try:
        rows = con.execute("PRAGMA compile_options").fetchall()
        out["sqlite_compile_options"] = sorted(r[0] for r in rows)
    except Exception:
        pass
    con.close()
except Exception as exc:
    out["sqlite_error"] = str(exc)

try:
    from importlib.metadata import version, PackageNotFoundError
    pkgs = {}
    for name in __PKGS__:
        try:
            pkgs[name] = version(name)
        except PackageNotFoundError:
            pkgs[name] = "<missing>"
        except Exception as exc:
            pkgs[name] = "<error: %s>" % exc
    out["packages"] = pkgs
except Exception as exc:
    out["packages_error"] = str(exc)

try:
    import av
    out["pyav_version"] = getattr(av, "__version__", "<unknown>")
    libs = getattr(av, "library_versions", None)
    if libs:
        out["pyav_ffmpeg_libs"] = {k: ".".join(str(n) for n in v) if isinstance(v, tuple) else str(v)
                                   for k, v in sorted(libs.items())}
except Exception as exc:
    out["pyav_error"] = str(exc)

try:
    from pymediainfo import MediaInfo
    out["mediainfo_library_available"] = bool(MediaInfo.can_parse())
    try:
        import pymediainfo, pathlib
        base = pathlib.Path(pymediainfo.__file__).parent
        out["mediainfo_bundled_libs"] = sorted(
            p.name for p in base.iterdir()
            if p.suffix.lower() in (".dll", ".so", ".dylib")
        )
    except Exception:
        pass
except Exception as exc:
    out["pymediainfo_error"] = str(exc)

try:
    import app.config as _cfg  # 项目自身配置解析结果
    out["app_data_dir"] = str(_cfg.settings.data_dir)
    out["app_db_path"] = str(_cfg.settings.db_path)
    out["app_port_default"] = _cfg.settings.port
except Exception as exc:
    out["app_config_error"] = str(exc)

print("__TAGHIVE_PROBE__" + json.dumps(out, ensure_ascii=False, default=str))
'''
    probe = probe.replace("__PKGS__", json.dumps(PY_KEY_PACKAGES))

    exe = python_exe if python_exe and Path(python_exe).exists() else None
    if exe is None:
        exe = shutil.which(python_exe or "") or sys.executable

    try:
        proc = subprocess.run(
            [exe, "-c", probe],
            capture_output=True,
            timeout=90,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(root / "src-python"),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"probe_error": str(exc), "probe_python": exe}

    marker = "__TAGHIVE_PROBE__"
    payload = next(
        (line[len(marker):] for line in (proc.stdout or "").splitlines() if line.startswith(marker)),
        None,
    )
    if not payload:
        return {
            "probe_error": "探针未返回结果",
            "probe_python": exe,
            "stdout_tail": (proc.stdout or "")[-800:],
            "stderr_tail": (proc.stderr or "")[-800:],
        }
    try:
        result = json.loads(payload)
    except ValueError as exc:
        return {"probe_error": f"结果解析失败: {exc}", "probe_python": exe}
    result["probe_python"] = exe
    if proc.stderr and proc.stderr.strip():
        result["probe_stderr_tail"] = proc.stderr.strip()[-500:]
    return result


def collect_dependency_locks(root: Path) -> dict[str, Any]:
    """采集依赖锁定状态与关键包的实际安装版本。

    ``Cargo.lock`` 未纳入版本控制（见 ``.gitignore``），且 ``package.json`` /
    ``Cargo.toml`` 使用了 ``^`` 与 caret 语义化范围，两台机器解析出的实际版本
    可能不同 —— 这会直接改变 Tauri/wry 行为与前端渲染。

    Args:
        root: 项目根目录。

    Returns:
        依赖信息字典。
    """
    info: dict[str, Any] = {}

    # --- 声明版本 ---
    tauri_conf = read_json(root / "src-tauri" / "tauri.conf.json")
    info["declared_versions"] = {
        "tauri.conf.json": (tauri_conf or {}).get("version") if isinstance(tauri_conf, dict) else None,
        "src-tauri/Cargo.toml": _toml_scalar(root / "src-tauri" / "Cargo.toml", "version"),
        "src-python/pyproject.toml": _toml_scalar(root / "src-python" / "pyproject.toml", "version"),
        "src-ui/package.json": ((read_json(root / "src-ui" / "package.json") or {}).get("version")),
    }

    # --- 锁文件指纹 ---
    locks = {
        "src-tauri/Cargo.lock": root / "src-tauri" / "Cargo.lock",
        "src-ui/package-lock.json": root / "src-ui" / "package-lock.json",
        "src-ui/pnpm-lock.yaml": root / "src-ui" / "pnpm-lock.yaml",
        "src-ui/yarn.lock": root / "src-ui" / "yarn.lock",
        "src-python/uv.lock": root / "src-python" / "uv.lock",
    }
    info["lockfiles"] = {name: describe_path(p, digest=True) for name, p in locks.items()}

    # --- Cargo.lock 中关键 crate 的锁定版本 ---
    info["cargo_locked_crates"] = _parse_cargo_lock(root / "src-tauri" / "Cargo.lock")

    # --- node_modules 中实际安装的版本 ---
    info["ui_installed_packages"] = _installed_node_versions(root / "src-ui" / "node_modules")

    # --- venv 元信息 ---
    pyvenv_cfg = root / "src-python" / ".venv" / "pyvenv.cfg"
    info["pyvenv_cfg"] = _read_text_capped(pyvenv_cfg) or "<none>"
    return info


def _toml_scalar(path: Path, key: str) -> str | None:
    """从 TOML 文件的首个匹配行提取标量值（避免引入 toml 依赖）。

    Args:
        path: TOML 文件路径。
        key: 键名。

    Returns:
        去掉引号的值；未找到返回 ``None``。
    """
    if not path.exists():
        return None
    pattern = re.compile(rf'^\s*{re.escape(key)}\s*=\s*"([^"]+)"')
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = pattern.match(line)
            if m:
                return m.group(1)
    except OSError:
        return None
    return None


def _parse_cargo_lock(path: Path) -> dict[str, Any]:
    """解析 Cargo.lock，提取关注 crate 的锁定版本。

    Args:
        path: Cargo.lock 路径。

    Returns:
        crate 名到版本的映射；文件不存在返回说明字符串包装的字典。
    """
    if not path.exists():
        return {"_status": "<missing: 首次 cargo build 后生成>"}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"_status": f"<error: {exc}>"}

    versions: dict[str, str] = {}
    total = 0
    name: str | None = None
    for line in text.splitlines():
        line = line.strip()
        if line == "[[package]]":
            name = None
            total += 1
        elif line.startswith("name = "):
            name = line.partition("=")[2].strip().strip('"')
        elif line.startswith("version = ") and name:
            if name in CARGO_KEY_CRATES:
                versions[name] = line.partition("=")[2].strip().strip('"')
            name = None
    versions["_total_packages"] = str(total)
    for crate in CARGO_KEY_CRATES:
        versions.setdefault(crate, "<absent>")
    return dict(sorted(versions.items()))


def _installed_node_versions(node_modules: Path) -> dict[str, str]:
    """读取 node_modules 中关键包的实际安装版本。

    直接读磁盘上的 ``package.json``，比 ``npm ls`` 快且反映真实安装状态。

    Args:
        node_modules: node_modules 目录。

    Returns:
        包名到版本的映射。
    """
    if not node_modules.exists():
        return {"_status": "<missing: 需先 npm install>"}
    result: dict[str, str] = {}
    for pkg in UI_KEY_PACKAGES:
        meta = node_modules.joinpath(*pkg.split("/")) / "package.json"
        data = read_json(meta)
        result[pkg] = (
            data.get("version", "<no version field>")
            if isinstance(data, dict)
            else "<not installed>"
        )
    return result


def collect_env_vars() -> dict[str, Any]:
    """采集与构建 / 运行相关的环境变量。

    Returns:
        含变量表、PATH 分析与可疑目录提示的字典。
    """
    selected: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in ("PATH", "Path"):
            continue
        if key in ENV_EXACT or key.upper().startswith(tuple(p.upper() for p in ENV_PREFIXES)):
            # 代理与令牌类变量可能含凭据，仅标注长度
            if re.search(r"TOKEN|SECRET|PASSWORD|KEY$", key, re.IGNORECASE):
                selected[key] = f"<hidden, len={len(value)}>"
            else:
                selected[key] = value

    raw_path = os.environ.get("PATH", "")
    entries = [e for e in raw_path.split(os.pathsep) if e.strip()]
    suspicious = [
        e for e in entries if any(k in e.lower() for k in SUSPICIOUS_PATH_KEYWORDS)
    ]

    seen: set[str] = set()
    duplicates: list[str] = []
    for e in entries:
        norm = os.path.normcase(os.path.normpath(e))
        if norm in seen:
            duplicates.append(e)
        seen.add(norm)

    return {
        "selected": dict(sorted(selected.items())),
        "path_entry_count": len(entries),
        "path_entries": entries,
        "path_suspicious_entries": suspicious,
        "path_duplicate_entries": duplicates,
        "path_missing_entries": [e for e in entries if not Path(e).exists()],
        "shadowed_libraries": _find_shadowed_libs(entries),
    }


def _find_shadowed_libs(path_entries: list[str]) -> dict[str, list[str]]:
    """沿 PATH 查找可能相互抢占的动态库 / 可执行文件。

    背景：``scripts/build-sidecar.py`` 记录过 OpenSSL DLL 被 Anaconda / MSYS2
    抢占导致崩溃的问题；同一机制也会影响 MediaInfo 与 FFmpeg 的加载。

    Args:
        path_entries: PATH 中的目录列表。

    Returns:
        库名到命中路径列表的映射，只保留命中数 ≥ 1 的项。
    """
    hits: dict[str, list[str]] = {}
    for lib in SHADOWED_LIBS:
        found: list[str] = []
        for entry in path_entries:
            candidate = Path(entry) / lib
            try:
                if candidate.exists():
                    found.append(str(candidate))
            except OSError:
                continue
            if len(found) >= 5:
                break
        if found:
            hits[lib] = found
    return hits


def collect_runtime_state(root: Path) -> dict[str, Any]:
    """采集端口占用、数据目录与日志现状。

    Args:
        root: 项目根目录。

    Returns:
        运行时状态字典。
    """
    info: dict[str, Any] = {
        "ports": {
            "5173 (vite dev)": port_state(5173),
            **{f"{p} (sidecar)": port_state(p) for p in range(8721, 8726)},
        }
    }

    data_dirs = [root / ".taghive" / "data", root / "src-python" / ".taghive", root / ".taghive"]
    dbs: dict[str, Any] = {}
    for d in data_dirs:
        if not d.exists():
            continue
        for db in sorted(d.glob("*.db")):
            dbs[str(db)] = _inspect_sqlite(db)
    info["databases"] = dbs or {"_status": "<未发现数据库文件>"}

    logs_dir = root / ".taghive" / "logs"
    if logs_dir.exists():
        info["log_files"] = {
            p.name: describe_path(p)
            for p in sorted(logs_dir.glob("*"), key=lambda x: x.name)[:20]
        }
    else:
        info["log_files"] = {"_status": "<无日志目录>"}

    info["cwd"] = os.getcwd()
    info["project_root"] = str(root)
    info["project_root_drive"] = os.path.splitdrive(str(root))[0] or "/"
    info["project_path_length"] = len(str(root))
    info["project_path_ascii_only"] = str(root).isascii()
    return info


def _inspect_sqlite(db: Path) -> dict[str, Any]:
    """以只读方式检查 SQLite 数据库的规模与关键表。

    Args:
        db: 数据库文件路径。

    Returns:
        含大小、表清单与行数统计的字典。
    """
    import sqlite3

    out: dict[str, Any] = {"size_bytes": db.stat().st_size if db.exists() else None}
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error as exc:
        out["error"] = str(exc)
        return out
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
        )]
        out["tables"] = tables
        out["user_version"] = con.execute("PRAGMA user_version").fetchone()[0]
        out["journal_mode"] = con.execute("PRAGMA journal_mode").fetchone()[0]
        counts: dict[str, Any] = {}
        for t in ("files", "tags", "file_tags", "workspaces", "files_fts"):
            if t in tables:
                try:
                    counts[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                except sqlite3.Error as exc:
                    counts[t] = f"<error: {exc}>"
        out["row_counts"] = counts
    except sqlite3.Error as exc:
        out["error"] = str(exc)
    finally:
        con.close()
    return out


def collect_git(root: Path) -> dict[str, Any]:
    """采集 Git 工作区状态与影响文件内容的配置。

    ``core.autocrlf`` 在不同机器取值不同时，签出的换行符会不同，可能改变
    脚本、CSS 甚至字符串字面量的实际内容。

    Args:
        root: 项目根目录。

    Returns:
        Git 信息字典。
    """
    def git(*args: str) -> str | None:
        """在项目根目录执行 git 子命令。"""
        return run(["git", *args], cwd=root)

    status = git("status", "--porcelain=v1") or ""
    dirty = [line for line in status.splitlines() if line.strip()]
    return {
        "branch": first_line(git("rev-parse", "--abbrev-ref", "HEAD")),
        "head": first_line(git("rev-parse", "HEAD")),
        "head_subject": first_line(git("log", "-1", "--pretty=%s")),
        "head_date": first_line(git("log", "-1", "--pretty=%cI")),
        "upstream": first_line(git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")),
        "ahead_behind": first_line(git("rev-list", "--left-right", "--count", "HEAD...@{u}")),
        "dirty_file_count": len(dirty),
        "dirty_files": dirty[:40],
        "remote_origin": first_line(git("remote", "get-url", "origin")),
        "config": {
            key: first_line(git("config", "--get", key)) or "<unset>"
            for key in (
                "core.autocrlf",
                "core.eol",
                "core.filemode",
                "core.symlinks",
                "core.longpaths",
                "core.ignorecase",
                "core.fsmonitor",
                "user.name",
            )
        },
    }


def build_report() -> dict[str, Any]:
    """采集全部信息并组装报告。

    Returns:
        完整报告字典。
    """
    started = time.time()
    root = project_root()

    py_resolution = collect_python_resolution(root)
    report: dict[str, Any] = {
        "report": {
            "schema_version": REPORT_SCHEMA_VERSION,
            "tool": "scripts/env-report.py",
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "host": collect_host(),
        "webview": collect_webview(),
        "toolchain": collect_toolchain(),
        "local_config": collect_local_config(root),
        "python_resolution": py_resolution,
        "python_runtime": collect_python_runtime(py_resolution.get("effective_python"), root),
        "dependencies": collect_dependency_locks(root),
        "env": collect_env_vars(),
        "runtime": collect_runtime_state(root),
        "git": collect_git(root),
    }
    report["report"]["elapsed_seconds"] = round(time.time() - started, 2)
    report["fingerprint"] = _fingerprint(report)
    report["findings"] = analyze(report)
    return report


def _fingerprint(report: dict[str, Any]) -> dict[str, str]:
    """基于关键字段生成短指纹，便于一眼判断两台机器是否等价。

    Args:
        report: 已采集的报告。

    Returns:
        分类指纹字典。
    """
    def digest(obj: Any) -> str:
        """对任意可序列化对象取稳定短哈希。"""
        blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:10]

    tc = report["toolchain"]
    return {
        "toolchain": digest(
            {k: tc.get(k, {}).get("version") for k in ("rustc", "cargo", "node", "npm", "uv", "cargo_tauri")}
        ),
        "webview": digest(report["webview"].get("webview2_runtime_version")),
        "dependencies": digest(
            {
                "cargo": report["dependencies"]["cargo_locked_crates"],
                "ui": report["dependencies"]["ui_installed_packages"],
                "py": report["python_runtime"].get("packages"),
            }
        ),
        "local_config": digest(report["local_config"].get("src_tauri_config_json", {}).get("content")),
        "locale": digest(
            {
                k: report["host"].get(k)
                for k in ("preferred_encoding", "windows_code_page", "filesystem_encoding")
            }
        ),
        "git": digest(report["git"].get("head")),
    }


def analyze(report: dict[str, Any]) -> list[str]:
    """基于报告内容给出差异排查提示。

    仅做本机自查（缺失、冲突、非默认配置），跨机器对比请使用 ``--compare``。

    Args:
        report: 已采集的报告。

    Returns:
        提示信息列表，按重要性从高到低排列。
    """
    notes: list[str] = []

    cfg = report["local_config"].get("src_tauri_config_json", {})
    if cfg.get("exists"):
        notes.append(
            "src-tauri/config.json 存在且未纳入 Git —— 它会覆盖 Python 路径与数据目录，"
            "是跨机差异的首要嫌疑，请与另一台机器逐字段对比"
        )
    else:
        notes.append("src-tauri/config.json 不存在，Python 走 .venv/系统解释器回退路径")

    pr = report["python_resolution"]
    if str(pr.get("effective_source") or "").startswith("system:"):
        notes.append(
            f"sidecar 将使用系统 Python（{pr.get('effective_python')}），"
            "其依赖版本不受 uv.lock 约束，极易与另一台机器不一致；建议 uv sync 创建 .venv"
        )

    rt = report["python_runtime"]
    if rt.get("sqlite_fts5") is not True:
        notes.append(f"SQLite FTS5 不可用（{rt.get('sqlite_fts5')}）—— files_fts 文件名搜索会失效")
    if "pyav_error" in rt:
        notes.append(f"PyAV 导入失败：{rt['pyav_error']} —— 视频缩略图与 ts 在线播放不可用")
    if rt.get("mediainfo_library_available") is False:
        notes.append("pymediainfo 找不到 MediaInfo 库 —— 时长提取会回退到 ffprobe 或失败")
    if str((rt.get("packages") or {}).get("av", "")).startswith("<"):
        notes.append("av 包未安装 —— 视频相关功能会静默降级")

    wv = report["webview"].get("webview2_runtime_version")
    if wv == "<not found>" and IS_WINDOWS:
        notes.append("未检测到 WebView2 Runtime 注册表项 —— dev 模式可能无法创建窗口")

    host = report["host"]
    if IS_WINDOWS:
        if host.get("windows_utf8_beta_enabled"):
            notes.append(
                "系统开启了 UTF-8 Beta（ACP=65001）—— 与未开启的机器相比，"
                "sidecar 日志编码与中文路径处理行为不同"
            )
        if str(host.get("long_paths_enabled")) != "1":
            notes.append("Windows 长路径未启用 —— 深层目录扫描可能失败")
        scale = host.get("display_scale")
        if scale and scale != "100%":
            notes.append(f"显示缩放为 {scale} —— WebView 布局与另一台 100% 缩放的机器观感不同")

    env = report["env"]
    if env["path_suspicious_entries"]:
        notes.append(
            "PATH 含 conda/MSYS2 等目录："
            + ", ".join(env["path_suspicious_entries"][:3])
            + " —— 可能抢占 OpenSSL / MediaInfo / FFmpeg 动态库"
        )
    for lib, paths in env["shadowed_libraries"].items():
        if len(paths) > 1:
            notes.append(f"PATH 上存在多份 {lib}（{len(paths)} 处），首个生效：{paths[0]}")

    taghive_env = {k: v for k, v in env["selected"].items() if k.startswith("TAGHIVE_")}
    if taghive_env:
        notes.append(f"检测到 TAGHIVE_* 环境变量覆盖：{taghive_env} —— 优先级高于配置文件")

    ports = report["runtime"]["ports"]
    busy = [name for name, state in ports.items() if state == "in_use"]
    if busy:
        notes.append(
            f"端口已被占用：{', '.join(busy)} —— sidecar 会自动避让到其他端口，"
            "但 Vite 代理固定指向 8721，浏览器 dev 模式下会失配"
        )

    ui_pkgs = report["dependencies"]["ui_installed_packages"]
    if ui_pkgs.get("_status"):
        notes.append("src-ui/node_modules 缺失 —— 需先 npm install")
    lock = report["dependencies"]["lockfiles"]
    if not lock.get("src-ui/package-lock.json", {}).get("exists"):
        notes.append("package-lock.json 缺失 —— 前端依赖版本无法在多机之间固定")
    if not lock.get("src-tauri/Cargo.lock", {}).get("exists"):
        notes.append("Cargo.lock 缺失 —— Rust 依赖将重新解析，可能拉到不同的 tauri/wry 小版本")

    versions = report["dependencies"]["declared_versions"]
    release = {k: v for k, v in versions.items() if k != "src-ui/package.json"}
    if len(set(release.values())) > 1:
        notes.append(f"发布版本号不一致：{release}")

    git = report["git"]
    if git.get("dirty_file_count"):
        notes.append(f"工作区有 {git['dirty_file_count']} 个未提交改动 —— 对比前先确认代码一致")
    autocrlf = git.get("config", {}).get("core.autocrlf")
    if autocrlf not in (None, "<unset>", "false", "input"):
        notes.append(f"core.autocrlf={autocrlf} —— 换行符会被改写，与其他机器的签出内容可能不同")

    return notes


# --------------------------------------------------------------------------- #
# 渲染与对比
# --------------------------------------------------------------------------- #


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """把嵌套结构压平成点分键，便于逐项对比。

    Args:
        obj: 任意嵌套的字典 / 列表 / 标量。
        prefix: 当前键前缀。

    Returns:
        点分键到标量值的映射。
    """
    flat: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            flat.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        if all(not isinstance(x, (dict, list)) for x in obj):
            flat[prefix] = " | ".join(str(x) for x in obj)
        else:
            for i, v in enumerate(obj):
                flat.update(flatten(v, f"{prefix}[{i}]"))
    else:
        flat[prefix] = obj
    return flat


def is_volatile(key: str) -> bool:
    """判断字段是否属于无诊断价值的易变项。

    Args:
        key: 点分键。

    Returns:
        易变则返回 ``True``。
    """
    if key in VOLATILE_KEYS or key.endswith(VOLATILE_SUFFIXES):
        return True
    return any(part in key for part in VOLATILE_SUBSTRINGS)


def render_text(report: dict[str, Any]) -> str:
    """把报告渲染成可读文本。

    Args:
        report: 报告字典。

    Returns:
        多行文本。
    """
    lines: list[str] = []
    meta = report["report"]
    host = report["host"]
    lines.append("=" * 78)
    lines.append(f" TagHive 开发环境报告  |  {host['hostname']}  |  {meta['generated_at']}")
    lines.append("=" * 78)

    lines.append("")
    lines.append("[指纹] 与另一台机器逐项比对，不同者即为差异来源")
    for k, v in report["fingerprint"].items():
        lines.append(f"  {k:<14} {v}")

    if report["findings"]:
        lines.append("")
        lines.append("[排查提示]")
        for i, note in enumerate(report["findings"], 1):
            lines.append(f"  {i:>2}. {note}")

    sections = [
        ("主机与区域设置", report["host"]),
        ("WebView / 渲染引擎", report["webview"]),
        ("工具链", report["toolchain"]),
        ("本地未受版本控制的配置", report["local_config"]),
        ("Python 解释器解析（复刻 sidecar.rs）", report["python_resolution"]),
        ("Python 运行时探针", report["python_runtime"]),
        ("依赖与锁定", report["dependencies"]),
        ("环境变量与 PATH", report["env"]),
        ("运行时状态", report["runtime"]),
        ("Git", report["git"]),
    ]
    for title, payload in sections:
        lines.append("")
        lines.append(f"── {title} " + "─" * max(4, 70 - len(title)))
        for key, value in flatten(payload).items():
            text = "<none>" if value is None else str(value)
            if len(text) > 300:
                text = f"{text[:300]}...<truncated>"
            lines.append(f"  {key:<46} {text}")

    lines.append("")
    lines.append("=" * 78)
    return "\n".join(lines)


def compare_reports(path_a: Path, path_b: Path, show_all: bool = False) -> str:
    """对比两份报告并输出差异。

    Args:
        path_a: 报告 A 的 JSON 路径。
        path_b: 报告 B 的 JSON 路径。
        show_all: 为 ``True`` 时同时列出相同项。

    Returns:
        对比结果文本。
    """
    a = read_json(path_a)
    b = read_json(path_b)
    for name, data in ((path_a, a), (path_b, b)):
        if not isinstance(data, dict):
            return f"无法读取报告: {name} ({data})"

    label_a = a.get("host", {}).get("hostname", path_a.name)
    label_b = b.get("host", {}).get("hostname", path_b.name)

    fa, fb = flatten(a), flatten(b)
    keys = sorted(set(fa) | set(fb))

    diffs: list[tuple[str, Any, Any]] = []
    same = 0
    for key in keys:
        if is_volatile(key):
            continue
        va, vb = fa.get(key, "<absent>"), fb.get(key, "<absent>")
        if va == vb:
            same += 1
            continue
        diffs.append((key, va, vb))

    lines = [
        "=" * 78,
        f" 环境对比  A={label_a}  ({path_a.name})",
        f"           B={label_b}  ({path_b.name})",
        "=" * 78,
        "",
        f"相同字段 {same} 项，差异字段 {len(diffs)} 项（已忽略时间戳 / 文件大小等易变项）",
    ]

    if a.get("report", {}).get("schema_version") != b.get("report", {}).get("schema_version"):
        lines.append("警告：两份报告的 schema_version 不同，字段含义可能不可比")

    fp_a = a.get("fingerprint", {})
    fp_b = b.get("fingerprint", {})
    lines.append("")
    lines.append("[指纹对比]")
    for key in sorted(set(fp_a) | set(fp_b)):
        mark = "==" if fp_a.get(key) == fp_b.get(key) else "!="
        lines.append(f"  {key:<14} {fp_a.get(key, '-'):<12} {mark} {fp_b.get(key, '-')}")

    # 按顶层分组归类差异，便于定位
    grouped: dict[str, list[tuple[str, Any, Any]]] = {}
    for key, va, vb in diffs:
        grouped.setdefault(key.split(".", 1)[0], []).append((key, va, vb))

    priority = [
        "local_config",
        "python_resolution",
        "python_runtime",
        "dependencies",
        "webview",
        "toolchain",
        "host",
        "env",
        "runtime",
        "git",
        "findings",
        "fingerprint",
        "report",
    ]
    ordered = sorted(grouped, key=lambda g: (priority.index(g) if g in priority else 99, g))

    for group in ordered:
        lines.append("")
        lines.append(f"── {group} （{len(grouped[group])} 处差异） " + "─" * 30)
        for key, va, vb in grouped[group]:
            lines.append(f"  {key}")
            lines.append(f"      A: {_clip(va)}")
            lines.append(f"      B: {_clip(vb)}")

    if show_all:
        lines.append("")
        lines.append("── 相同字段 " + "─" * 50)
        for key in keys:
            if is_volatile(key) or fa.get(key) != fb.get(key):
                continue
            lines.append(f"  {key:<46} {_clip(fa.get(key))}")

    lines.append("")
    lines.append("=" * 78)
    return "\n".join(lines)


def _clip(value: Any, limit: int = 220) -> str:
    """把值转为单行字符串并截断。

    Args:
        value: 任意值。
        limit: 最大长度。

    Returns:
        截断后的字符串。
    """
    text = "<none>" if value is None else str(value)
    text = text.replace("\n", "\\n")
    return text if len(text) <= limit else f"{text[:limit]}...<truncated>"


def main() -> int:
    """命令行入口。

    Returns:
        进程退出码，0 表示成功。
    """
    if IS_WINDOWS:
        # 在 argparse 之前切到 UTF-8，避免 GBK 控制台把 --help 与框线字符打成乱码
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
            except (AttributeError, OSError):
                pass

    parser = argparse.ArgumentParser(
        description="输出 TagHive 开发环境的完整配置，用于定位 cargo tauri dev 的跨机差异",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python scripts/env-report.py\n"
            "  python scripts/env-report.py --json my-pc.json\n"
            "  python scripts/env-report.py --compare pc-a.json pc-b.json\n"
        ),
    )
    parser.add_argument("--json", metavar="PATH", help="JSON 报告输出路径")
    parser.add_argument("--no-save", action="store_true", help="不写入默认 JSON 文件")
    parser.add_argument("--quiet", action="store_true", help="只输出提示与指纹，不打印全部字段")
    parser.add_argument(
        "--compare", nargs=2, metavar=("A.json", "B.json"), help="对比两份已生成的报告"
    )
    parser.add_argument("--all", action="store_true", help="配合 --compare，同时列出相同字段")
    args = parser.parse_args()

    if args.compare:
        print(compare_reports(Path(args.compare[0]), Path(args.compare[1]), show_all=args.all))
        return 0

    report = build_report()

    if args.quiet:
        print(f"主机: {report['host']['hostname']}  |  {report['report']['generated_at']}")
        print("[指纹]")
        for k, v in report["fingerprint"].items():
            print(f"  {k:<14} {v}")
        print("[排查提示]")
        for i, note in enumerate(report["findings"], 1):
            print(f"  {i:>2}. {note}")
    else:
        print(render_text(report))

    out_path: Path | None = None
    if args.json:
        out_path = Path(args.json)
    elif not args.no_save:
        host = re.sub(r"[^\w.-]", "_", report["host"]["hostname"] or "unknown")
        out_path = project_root() / ".taghive" / f"env-report-{host}.json"

    if out_path:
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            print(f"\nJSON 报告已写入: {out_path}")
            print("把两台机器的 JSON 收集到一起后执行：")
            print(f"  python scripts/env-report.py --compare <A>.json <B>.json")
        except OSError as exc:
            print(f"\n写入 JSON 失败: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
