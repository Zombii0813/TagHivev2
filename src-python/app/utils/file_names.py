"""文件及目录共用的名称校验。"""

import re


def validate_name(value: str) -> str:
    """验证单个跨平台名称，拒绝路径及 Windows 保留名称。

    Args:
        value: 用户提交的文件或目录名称。

    Returns:
        验证后的原始名称。

    Raises:
        ValueError: 名称无效。
    """
    if (not value or value != value.strip() or value in {".", ".."}
            or value.endswith(".") or len(value) > 255
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
            or re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", value.split(".")[0])):
        raise ValueError("名称不能为空，不能包含路径、控制字符或系统保留名称")
    return value
