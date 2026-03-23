"""Tester 에이전트 - 코드 검증 및 실제 실행"""

import ast
import math
import re
import traceback

from .base import AgentBase


# exec() 실행 시 차단할 모듈
BLOCKED_MODULES = frozenset({
    "os", "subprocess", "sys", "shutil", "pathlib",
    "socket", "http", "ftplib", "smtplib", "ctypes",
    "multiprocessing", "signal",
})

# exec()에서 허용할 안전한 builtins만
SAFE_BUILTINS = {
    "True": True, "False": False, "None": None,
    "range": range, "len": len, "print": print,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    "int": int, "float": float, "str": str, "bool": bool,
    "max": max, "min": min, "abs": abs, "round": round,
    "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    "sorted": sorted, "reversed": reversed,
    "isinstance": isinstance, "issubclass": issubclass,
    "hasattr": hasattr, "sum": sum, "any": any, "all": all,
    "pow": pow, "divmod": divmod,
    "ValueError": ValueError, "TypeError": TypeError,
    "RuntimeError": RuntimeError, "KeyError": KeyError,
    "IndexError": IndexError, "AttributeError": AttributeError,
    "Exception": Exception,
}


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
    def check_code_safety(code: str) -> str | None:
        """AST 기반으로 위험한 코드를 검사한다."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"문법 오류 (라인 {e.lineno}): {e.msg}"

        for node in ast.walk(tree):
            # import 검사
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split(".")[0]
                    if mod in BLOCKED_MODULES:
                        return f"차단된 모듈: {mod} (라인 {node.lineno})"

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod = node.module.split(".")[0]
                    if mod in BLOCKED_MODULES:
                        return f"차단된 모듈: {mod} (라인 {node.lineno})"

            # __import__() 호출 차단
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in ("__import__", "eval", "exec", "compile", "open"):
                    return f"차단된 함수: {func.id}() (라인 {node.lineno})"
                if isinstance(func, ast.Attribute) and func.attr in ("__import__", "system", "popen"):
                    return f"차단된 함수: {func.attr}() (라인 {node.lineno})"

        return None

    @staticmethod
    def execute_code(code: str) -> dict:
        """Blender 메인 스레드에서 코드를 실행하고 결과를 반환한다.

        주의: 이 함수는 반드시 메인 스레드에서 호출해야 한다.

        Returns:
            {"success": bool, "error": str | None}
        """
        # AST 기반 안전성 검사
        safety_error = TesterAgent.check_code_safety(code)
        if safety_error:
            return {"success": False, "error": safety_error}

        try:
            import bpy
            import mathutils
            import bmesh

            # 실행 전 undo 포인트 생성 (실패해도 코드 실행은 계속)
            try:
                bpy.ops.ed.undo_push(message="NUP Modeling: Before Test")
            except RuntimeError:
                pass  # context가 맞지 않는 경우 무시

            # 안전한 globals로 실행
            safe_globals = dict(SAFE_BUILTINS)
            safe_globals["bpy"] = bpy
            safe_globals["mathutils"] = mathutils
            safe_globals["bmesh"] = bmesh
            safe_globals["math"] = math

            exec(code, {"__builtins__": safe_globals})
            return {"success": True, "error": None}
        except SyntaxError as e:
            return {"success": False, "error": f"문법 오류 (라인 {e.lineno}): {e.msg}"}
        except Exception as e:
            tb = traceback.format_exc()
            # 민감 정보 필터링
            filtered_tb = "\n".join(
                line for line in tb.splitlines()
                if "api_key" not in line.lower()
            )
            return {"success": False, "error": f"{type(e).__name__}: {e}\n{filtered_tb}"}
