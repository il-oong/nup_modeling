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
        "- if __name__ == '__main__': 사용 → exec() 환경에서 NameError 발생. [FAIL] 처리.\n"
        "- bpy.ops.object.select_all(action='SELECT') + delete() → 기존 작업물 삭제 위험. [FAIL] 처리.\n"
        "- bpy.context.collection.objects.new() → AttributeError. bpy.data.objects.new() + link() 사용해야 함. [FAIL] 처리.\n"
        "- bmesh.ops.create_cone(diameter1=...) → TypeError. radius1/radius2 사용해야 함. [FAIL] 처리.\n"
        "- bpy.ops.node.new_geometry_nodes_modifier() → 컨텍스트 오류. 수동 노드그룹 생성 필요. [FAIL] 처리.\n"
        "- gn_mod.node_group 접근 전 None 체크 없음 → AttributeError 가능. [FAIL] 처리.\n"
        "- Principled BSDF 입력에 직접 인덱싱 (bsdf.inputs['Specular IOR Level'] 등) → KeyError. [FAIL] 처리.\n"
        "  반드시 in 또는 .get()으로 존재 확인 후 접근해야 함."
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
        error = TesterAgent._check_blender_patterns(tree, code)
        if error:
            return error

        return None

    @staticmethod
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
                        # 부모가 bmesh 변수일 가능성 체크
                        return (f"BMesh {attr} 슬라이싱 사용 불가 → TypeError 위험 "
                                f"(라인 {node.lineno})")

            # --- 6. Principled BSDF 직접 인덱싱 검사 ---
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
                if node.value.attr == "inputs" and isinstance(node.slice, ast.Constant):
                    socket_name = node.slice.value
                    # Blender 4.x 전용 소켓명을 3.x에서 쓰면 KeyError
                    BSDF_4X_ONLY = {
                        "Subsurface Weight", "Specular IOR Level",
                        "Transmission Weight", "Coat Weight", "Coat Roughness",
                        "Emission Color", "Sheen Weight", "Sheen Roughness",
                    }
                    if socket_name in BSDF_4X_ONLY:
                        return (f"Principled BSDF 입력 '{socket_name}'은 Blender 4.x 전용, "
                                f"3.x에서 KeyError 발생. in/.get()으로 확인 필요 (라인 {node.lineno})")

        # --- 7. if __name__ == '__main__' 검사 ---
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                test = node.test
                if isinstance(test, ast.Compare):
                    if (isinstance(test.left, ast.Name) and test.left.id == "__name__"
                            and any(isinstance(c, ast.Constant) and c.value == "__main__"
                                    for c in test.comparators)):
                        return f"if __name__ == '__main__' 사용 금지 (라인 {node.lineno})"

        # --- 8. 전체 삭제 패턴 검사 (select_all SELECT + delete) ---
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "select_all(action='SELECT')" in stripped or 'select_all(action="SELECT")' in stripped:
                # 다음 몇 줄 내에 delete()가 있는지
                for j in range(i, min(i + 5, len(lines) + 1)):
                    if j - 1 < len(lines) and "delete()" in lines[j - 1]:
                        return f"전체 선택 후 삭제 패턴 감지 - 기존 작업물 삭제 위험 (라인 {i})"

        # --- 9. 모디파이어 적용 루프 검사 (for mod in obj.modifiers + apply) ---
        for node in ast.walk(tree):
            if isinstance(node, ast.For):
                # for mod in X.modifiers: ... modifier_apply 패턴
                if (isinstance(node.iter, ast.Attribute) and node.iter.attr == "modifiers"):
                    for inner in ast.walk(node):
                        if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                                and inner.func.attr == "modifier_apply"):
                            return (f"for 루프에서 modifiers 순회 중 modifier_apply → "
                                    f"컬렉션 변경으로 건너뜀 발생. while 사용 필요 (라인 {node.lineno})")

        return None


def _is_attr_call(call_node: ast.Call, obj_path: str, method: str) -> bool:
    """AST Call 노드가 특정 객체.메서드() 호출인지 확인한다.
    예: _is_attr_call(node, "bpy.ops.node", "new_geometry_nodes_modifier")
    """
    func = call_node.func
    if not isinstance(func, ast.Attribute) or func.attr != method:
        return False

    # obj_path를 역순으로 매칭
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
            # 민감 정보 필터링
            filtered_tb = "\n".join(
                line for line in tb.splitlines()
                if "api_key" not in line.lower()
            )
            return {"success": False, "error": f"{type(e).__name__}: {e}\n{filtered_tb}"}
