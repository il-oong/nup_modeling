"""Tester 에이전트 - 코드 검증 및 실제 실행"""

import re
import traceback

from .base import AgentBase


# exec() 실행 시 차단할 모듈
BLOCKED_MODULES = {"os", "subprocess", "sys", "shutil", "pathlib", "socket", "http", "ftplib"}


class TesterAgent(AgentBase):
    name = "Tester"
    icon = "CHECKMARK"

    system_prompt = (
        "당신은 Blender Python 코드 검증 전문가입니다.\n"
        "코드의 문법 오류, bpy API 호환성, 런타임 에러를 분석합니다.\n\n"
        "역할:\n"
        "- 코드 문법 검증\n"
        "- bpy API 사용법 검증\n"
        "- 잠재적 런타임 오류 분석\n"
        "- 실행 결과 리포트\n\n"
        "규칙:\n"
        "- 오류가 있으면 구체적으로 어떤 줄에서 무엇이 잘못되었는지 설명한다.\n"
        "- 오류가 없으면 'PASS'라고 명시한다.\n"
        "- 한국어로 답변한다.\n"
        "- 결과를 [PASS] 또는 [FAIL]로 시작한다."
    )

    @staticmethod
    def extract_code(text: str) -> str | None:
        """텍스트에서 python 코드 블록을 추출한다."""
        pattern = r"```python\s*\n(.*?)```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def check_blocked_imports(code: str) -> str | None:
        """위험한 모듈 import를 검사한다."""
        for line in code.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                for module in BLOCKED_MODULES:
                    if module in stripped:
                        return f"차단된 모듈 사용: {module} (라인: {stripped})"
        return None

    @staticmethod
    def execute_code(code: str) -> dict:
        """Blender 내에서 코드를 실행하고 결과를 반환한다.

        Returns:
            {"success": bool, "error": str | None}
        """
        # 위험한 import 검사
        blocked = TesterAgent.check_blocked_imports(code)
        if blocked:
            return {"success": False, "error": blocked}

        try:
            import bpy
            # 실행 전 undo 포인트 생성
            bpy.ops.ed.undo_push(message="NUP Modeling: Before Test")
            exec(code, {"__builtins__": __builtins__, "bpy": __import__("bpy")})
            return {"success": True, "error": None}
        except SyntaxError as e:
            return {"success": False, "error": f"문법 오류 (라인 {e.lineno}): {e.msg}"}
        except Exception as e:
            tb = traceback.format_exc()
            return {"success": False, "error": f"{type(e).__name__}: {e}\n{tb}"}
