"""exec() 안전 실행 유틸리티"""

BLOCKED_MODULES = frozenset({
    "os", "subprocess", "sys", "shutil", "pathlib",
    "socket", "http", "ftplib", "smtplib", "ctypes",
    "multiprocessing", "signal",
})


def is_safe_code(code: str) -> tuple[bool, str]:
    """코드에 위험한 import가 포함되어 있는지 검사한다.

    Returns:
        (안전 여부, 오류 메시지)
    """
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            for module in BLOCKED_MODULES:
                # "import os" 또는 "from os import ..." 패턴 체크
                if f"import {module}" in stripped or f"from {module}" in stripped:
                    return False, f"차단된 모듈: {module}"
    return True, ""
