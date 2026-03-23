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

# exec() 내에서 import 허용할 모듈
ALLOWED_MODULES = frozenset({
    "bpy", "bmesh", "mathutils", "math", "random",
    "collections", "functools", "itertools",
    "bpy.types", "bpy.props", "bpy.ops",
    "mathutils.noise",
})

# exec()에서 허용할 안전한 builtins만
SAFE_BUILTINS = {
    "True": True, "False": False, "None": None,
    "range": range, "len": len, "print": print,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    "frozenset": frozenset, "bytes": bytes, "bytearray": bytearray,
    "int": int, "float": float, "str": str, "bool": bool, "complex": complex,
    "max": max, "min": min, "abs": abs, "round": round,
    "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    "sorted": sorted, "reversed": reversed,
    "isinstance": isinstance, "issubclass": issubclass,
    "hasattr": hasattr, "getattr": getattr, "setattr": setattr,
    "sum": sum, "any": any, "all": all,
    "type": type, "super": super, "object": object,
    "iter": iter, "next": next,
    "repr": repr, "id": id, "hash": hash,
    "chr": chr, "ord": ord, "hex": hex, "oct": oct,
    "format": format, "slice": slice,
    "pow": pow, "divmod": divmod,
    "property": property, "staticmethod": staticmethod, "classmethod": classmethod,
    "ValueError": ValueError, "TypeError": TypeError,
    "RuntimeError": RuntimeError, "KeyError": KeyError,
    "IndexError": IndexError, "AttributeError": AttributeError,
    "ImportError": ImportError, "NameError": NameError,
    "StopIteration": StopIteration, "ZeroDivisionError": ZeroDivisionError,
    "NotImplementedError": NotImplementedError, "OSError": OSError,
    "Exception": Exception,
}

# Blender 4.x 전용 Principled BSDF 소켓명 (3.x에서 KeyError)
_BSDF_4X_ONLY = frozenset({
    "Subsurface Weight", "Specular IOR Level",
    "Transmission Weight", "Coat Weight", "Coat Roughness",
    "Emission Color", "Sheen Weight", "Sheen Roughness",
})


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
        "- 결과를 [PASS] 또는 [FAIL]로 시작한다.\n\n"
        "반드시 검사해야 할 BMesh 오류 패턴:\n"
        "- bm.verts[:], bm.faces[:], bm.edges[:] 슬라이싱 → TypeError 발생. [FAIL] 처리.\n"
        "- bm.verts[a:b], bm.faces[a:b] 범위 슬라이싱 → TypeError 발생. [FAIL] 처리.\n"
        "- bm.faces.get(), bm.verts.get() → AttributeError 발생. [FAIL] 처리.\n"
        "- face.vert_coords_get() → AttributeError. [v.co for v in face.verts] 사용해야 함. [FAIL] 처리.\n"
        "- ensure_lookup_table() 없이 인덱스 접근 → IndexError 가능. [FAIL] 처리.\n"
        "- bm.to_mesh() 또는 bm.free() 누락 → 메모리 누수. [FAIL] 처리.\n"
        "- modifier_apply 전 mode_set(mode='OBJECT') 누락 → RuntimeError 가능. [FAIL] 처리.\n\n"
        "반드시 검사해야 할 실행 환경 오류 패턴:\n"
        "- if __name__ == '__main__': 사용 → exec() 환경에서 실행 안 됨. [FAIL] 처리.\n"
        "- bpy.ops.object.select_all(action='SELECT') + delete() → 기존 작업물 삭제 위험. [FAIL] 처리.\n"
        "- bpy.context.collection.objects.new() → AttributeError. bpy.data.objects.new() + link() 사용해야 함. [FAIL] 처리.\n"
        "- bmesh.ops.create_cone(diameter1=...) → TypeError. radius1/radius2 사용해야 함. [FAIL] 처리.\n"
        "- bpy.ops.node.new_geometry_nodes_modifier() → 컨텍스트 오류. 수동 노드그룹 생성 필요. [FAIL] 처리.\n"
        "- gn_mod.node_group 접근 전 None 체크 없음 → AttributeError 가능. [FAIL] 처리.\n"
        "- Principled BSDF 입력 중 버전별로 다른 소켓만 가드 필요:\n"
        "  4.x 전용 (직접 접근 금지): Subsurface Weight, Specular IOR Level, Coat Weight, Emission Color\n"
        "  3.x 전용 (직접 접근 금지): Subsurface, Specular, Clearcoat, Emission\n"
        "  모든 버전에서 안전 (직접 접근 허용): Base Color, Roughness, Metallic, Normal, BSDF, IOR, Alpha\n"
        "  가드 필요 소켓은 if 'name' in inputs: 또는 .get()으로 접근해야 함. [FAIL] 처리."
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
        """AST 기반으로 위험한 코드와 알려진 런타임 오류 패턴을 검사한다."""
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

            # 위험 함수 호출 차단
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in ("__import__", "eval", "exec", "compile", "open"):
                    return f"차단된 함수: {func.id}() (라인 {node.lineno})"
                if isinstance(func, ast.Attribute) and func.attr in ("__import__", "system", "popen"):
                    return f"차단된 함수: {func.attr}() (라인 {node.lineno})"

        # 런타임 오류 패턴 정적 분석
        error = _check_blender_patterns(tree, code)
        if error:
            return error

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

            # 허용된 모듈만 import 가능한 커스텀 __import__
            _real_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

            def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
                root = name.split(".")[0]
                if root not in ALLOWED_MODULES and name not in ALLOWED_MODULES:
                    raise ImportError(f"차단된 모듈: {name}")
                return _real_import(name, globals, locals, fromlist, level)

            # 안전한 globals로 실행
            safe_globals = dict(SAFE_BUILTINS)
            safe_globals["bpy"] = bpy
            safe_globals["mathutils"] = mathutils
            safe_globals["bmesh"] = bmesh
            safe_globals["math"] = math
            safe_globals["__import__"] = _safe_import

            exec(code, {"__builtins__": safe_globals, "__name__": "__nup_exec__"})
            return {"success": True, "error": None}
        except SyntaxError as e:
            return {"success": False, "error": f"문법 오류 (라인 {e.lineno}): {e.msg}"}
        except Exception as e:
            tb = traceback.format_exc()
            filtered_tb = "\n".join(
                line for line in tb.splitlines()
                if "api_key" not in line.lower()
            )
            return {"success": False, "error": f"{type(e).__name__}: {e}\n{filtered_tb}"}

    @staticmethod
    def execute_code_stepwise(code: str, step_delay: float = 0.3) -> dict:
        """코드를 최상위 문 단위로 나눠서 타이머로 순차 실행한다.

        각 단계마다 뷰포트를 갱신하여 실시간 모델링 과정을 보여준다.

        Returns:
            {"success": bool, "error": str | None}
        """
        import bpy

        safety_error = TesterAgent.check_code_safety(code)
        if safety_error:
            return {"success": False, "error": safety_error}

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {"success": False, "error": f"문법 오류 (라인 {e.lineno}): {e.msg}"}

        # 최상위 문을 그룹으로 분할 (import/함수 정의는 한 그룹, 나머지는 개별)
        groups = []
        preamble = []  # import 및 함수/클래스 정의
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                                  ast.ClassDef, ast.Assign)):
                preamble.append(node)
            else:
                groups.append(node)

        # preamble은 첫 번째 그룹으로
        code_lines = code.splitlines(keepends=True)
        chunks = []

        if preamble:
            # preamble 전체를 하나의 청크로
            start = preamble[0].lineno - 1
            end = preamble[-1].end_lineno
            chunks.append("".join(code_lines[start:end]))

        for node in groups:
            start = node.lineno - 1
            end = node.end_lineno
            chunks.append("".join(code_lines[start:end]))

        if not chunks:
            chunks = [code]

        # 공유 실행 환경 구성
        import mathutils
        import bmesh

        _real_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            root = name.split(".")[0]
            if root not in ALLOWED_MODULES and name not in ALLOWED_MODULES:
                raise ImportError(f"차단된 모듈: {name}")
            return _real_import(name, globals, locals, fromlist, level)

        safe_globals = dict(SAFE_BUILTINS)
        safe_globals["bpy"] = bpy
        safe_globals["mathutils"] = mathutils
        safe_globals["bmesh"] = bmesh
        safe_globals["math"] = math
        safe_globals["__import__"] = _safe_import

        exec_namespace = {"__builtins__": safe_globals, "__name__": "__nup_exec__"}

        # 타이머로 순차 실행
        _step_state = {"index": 0, "error": None, "done": False}

        def _execute_next_step():
            idx = _step_state["index"]
            if idx >= len(chunks) or _step_state["error"]:
                _step_state["done"] = True
                return None  # 타이머 종료

            try:
                exec(chunks[idx], exec_namespace)
                # 뷰포트 갱신
                bpy.context.view_layer.update()
                for area in bpy.context.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
            except Exception as e:
                _step_state["error"] = f"{type(e).__name__}: {e}"
                _step_state["done"] = True
                return None

            _step_state["index"] = idx + 1
            if _step_state["index"] >= len(chunks):
                _step_state["done"] = True
                return None
            return step_delay  # 다음 단계까지 대기 시간

        bpy.app.timers.register(_execute_next_step, first_interval=0.1)
        return {"success": True, "error": None, "stepwise": True,
                "total_steps": len(chunks), "_state": _step_state}


# ── 정적 분석 헬퍼 (모듈 레벨 함수) ──

def _check_blender_patterns(tree: ast.AST, code: str) -> str | None:
    """알려진 Blender 런타임 오류 패턴을 AST로 검출한다."""
    lines = code.splitlines()

    for node in ast.walk(tree):
        # --- 1. bmesh.ops.create_cone(diameter1=...) 검사 ---
        if isinstance(node, ast.Call):
            if _is_attr_call(node, "bmesh.ops", "create_cone"):
                for kw in node.keywords:
                    if kw.arg in ("diameter1", "diameter2"):
                        return (f"bmesh.ops.create_cone: diameter1/diameter2 사용 불가, "
                                f"radius1/radius2 사용 필요 (라인 {node.lineno})")

            # --- 2. bpy.context.collection.objects.new() 검사 ---
            if _is_attr_call(node, "bpy.context.collection.objects", "new"):
                return (f"bpy.context.collection.objects.new() 사용 불가, "
                        f"bpy.data.objects.new() + link() 필요 (라인 {node.lineno})")

            # --- 3. bpy.ops.node.new_geometry_nodes_modifier() 검사 ---
            if _is_attr_call(node, "bpy.ops.node", "new_geometry_nodes_modifier"):
                return (f"bpy.ops.node.new_geometry_nodes_modifier() 컨텍스트 오류 위험, "
                        f"수동 노드그룹 생성 필요 (라인 {node.lineno})")

            # --- 4. face.vert_coords_get() 검사 ---
            if isinstance(node.func, ast.Attribute) and node.func.attr == "vert_coords_get":
                return (f"vert_coords_get() 존재하지 않음, "
                        f"[v.co for v in face.verts] 사용 필요 (라인 {node.lineno})")

        # --- 5. BMesh 슬라이싱 검사 (bm.verts[:], bm.faces[a:b]) ---
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            if isinstance(node.value, ast.Attribute):
                attr = node.value.attr
                if attr in ("verts", "faces", "edges"):
                    return (f"BMesh {attr} 슬라이싱 사용 불가 → TypeError 위험 "
                            f"(라인 {node.lineno})")

        # --- 6. Principled BSDF 직접 인덱싱 검사 ---
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            if node.value.attr == "inputs" and isinstance(node.slice, ast.Constant):
                socket_name = node.slice.value
                if isinstance(socket_name, str) and socket_name in _BSDF_4X_ONLY:
                    # 텍스트 레벨에서 가드 체크: 같은 소켓명의 in 체크가 근처에 있으면 안전
                    if not _is_socket_guarded(lines, node.lineno, socket_name):
                        return (f"Principled BSDF 입력 '{socket_name}'은 Blender 4.x 전용, "
                                f"3.x에서 KeyError 발생. in/.get()으로 확인 필요 (라인 {node.lineno})")

    # --- 7. if __name__ == '__main__' 검사 ---
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            test = node.test
            if (isinstance(test.left, ast.Name) and test.left.id == "__name__"
                    and any(isinstance(c, ast.Constant) and c.value == "__main__"
                            for c in test.comparators)):
                return f"if __name__ == '__main__' 사용 금지 (라인 {node.lineno})"

    # --- 8. 전체 삭제 패턴 검사 (select_all SELECT + delete) ---
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if "select_all(action='SELECT')" in stripped or 'select_all(action="SELECT")' in stripped:
            for j in range(i, min(i + 5, len(lines) + 1)):
                if j - 1 < len(lines) and "delete()" in lines[j - 1]:
                    return f"전체 선택 후 삭제 패턴 감지 - 기존 작업물 삭제 위험 (라인 {i})"

    # --- 9. 모디파이어 적용 루프 검사 (for mod in obj.modifiers + apply) ---
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            if isinstance(node.iter, ast.Attribute) and node.iter.attr == "modifiers":
                for inner in ast.walk(node):
                    if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                            and inner.func.attr == "modifier_apply"):
                        return (f"for 루프에서 modifiers 순회 중 modifier_apply → "
                                f"컬렉션 변경으로 건너뜀 발생. while 사용 필요 (라인 {node.lineno})")

    return None


def _is_socket_guarded(lines: list[str], target_lineno: int, socket_name: str) -> bool:
    """소켓 인덱싱이 'if/elif socket_name in inputs' 가드 안에 있는지 텍스트로 확인한다."""
    # 대상 줄 위로 5줄 범위 내에 가드 패턴이 있으면 안전
    guard_pattern = f"'{socket_name}' in"
    guard_pattern2 = f'"{socket_name}" in'
    # .get() 패턴도 안전
    get_pattern = f".get('{socket_name}')"
    get_pattern2 = f'.get("{socket_name}")'

    for i in range(max(0, target_lineno - 6), target_lineno):
        if i < len(lines):
            line = lines[i]
            if (guard_pattern in line or guard_pattern2 in line
                    or get_pattern in line or get_pattern2 in line):
                return True
    return False


def _is_attr_call(call_node: ast.Call, obj_path: str, method: str) -> bool:
    """AST Call 노드가 특정 객체.메서드() 호출인지 확인한다."""
    func = call_node.func
    if not isinstance(func, ast.Attribute) or func.attr != method:
        return False

    parts = obj_path.split(".")
    node = func.value
    for part in reversed(parts):
        if isinstance(node, ast.Attribute) and node.attr == part:
            node = node.value
        elif isinstance(node, ast.Name) and node.id == part:
            return True
        else:
            return False
    return True
