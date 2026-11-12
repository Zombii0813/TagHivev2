"""扫描及监听共用的根相对忽略规则。"""

from fnmatch import fnmatchcase
from pathlib import Path

IGNORED_PATTERNS = (".taghive", "sidecar.log", "*.db", "*.sqlite", "*.sqlite3",
                    "__pycache__", "*.pyc", ".git", ".idea", ".vscode",
                    "node_modules", ".pytest_cache")


def should_ignore(path: Path, root: Path | None = None) -> bool:
    """仅匹配根目录以下的完整路径段及文件名。

    Args:
        path: 待判断路径。
        root: 工作区根目录；根目录本身不参与匹配。

    Returns:
        是否应忽略该路径。
    """
    try:
        parts = path.relative_to(root).parts if root else path.parts
    except ValueError:
        return True
    return any(fnmatchcase(part.lower(), pattern) for part in parts for pattern in IGNORED_PATTERNS)
