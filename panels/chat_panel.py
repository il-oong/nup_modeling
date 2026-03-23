"""에이전트 대화 패널 - 접기/펼치기 + 상태 시각화"""

import bpy

# 에이전트별 아이콘 매핑
AGENT_ICONS = {
    "Architect": "CONSTRAINT",
    "Coder": "TEXT",
    "Tester": "CHECKMARK",
    "Reviewer": "VIEWZOOM",
    "Optimizer": "MODIFIER",
    "User": "USER",
    "System": "ERROR",
}


def _get_status_icon(content: str) -> str:
    """메시지 내용으로 상태 아이콘을 결정한다."""
    if "[PASS]" in content:
        return "CHECKMARK"
    elif "[FAIL]" in content:
        return "CANCEL"
    elif "[APPROVED]" in content:
        return "CHECKMARK"
    elif "[NEEDS_REVISION]" in content:
        return "ERROR"
    elif "[API 오류" in content or "[연결 오류" in content or "[오류]" in content:
        return "CANCEL"
    return ""


class NUP_OT_ToggleMessage(bpy.types.Operator):
    bl_idname = "nup.toggle_message"
    bl_label = "메시지 토글"
    bl_description = "메시지 상세 보기"

    index: bpy.props.IntProperty()

    def execute(self, context):
        scene = context.scene
        key = f"nup_msg_expanded_{self.index}"
        current = scene.get(key, False)
        scene[key] = not current
        return {"FINISHED"}


class NUP_PT_ChatPanel(bpy.types.Panel):
    bl_label = "에이전트 대화"
    bl_idname = "NUP_PT_ChatPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "NUP Modeling"
    bl_order = 1
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # 상단 버튼
        row = layout.row(align=True)
        op = row.operator("nup.copy_log", text="전체 로그 복사", icon="COPYDOWN")
        op.index = -1
        row.operator("nup.clear_messages", text="초기화", icon="TRASH")

        layout.separator()

        # ── 결과 상태 요약 ──
        if len(scene.nup_messages) > 0:
            status_box = layout.box()
            row = status_box.row()

            # 마지막 Tester 결과 찾기
            last_test = ""
            last_code_exists = False
            for msg in scene.nup_messages:
                if msg.role == "Tester":
                    last_test = msg.content
                if msg.is_code:
                    last_code_exists = True

            if "[PASS]" in last_test and "실행 성공" in last_test:
                row.label(text="상태: 성공", icon="CHECKMARK")
                status_box.label(text="모델이 3D 뷰포트에 생성되었습니다")
            elif "[FAIL]" in last_test:
                row.label(text="상태: 실패", icon="CANCEL")
                # 실패 원인 요약
                if "안전성" in last_test:
                    status_box.label(text="원인: 안전하지 않은 코드")
                elif "문법 오류" in last_test:
                    status_box.label(text="원인: Python 문법 오류")
                elif "재시도" in last_test:
                    status_box.label(text="원인: 최대 재시도 초과")
                else:
                    status_box.label(text="원인: 런타임 오류")
            elif scene.nup_is_running:
                row.label(text="상태: 진행 중...", icon="SORTTIME")
            elif last_code_exists:
                row.label(text="상태: 코드 생성됨", icon="FILE_SCRIPT")
            else:
                row.label(text="상태: 대기 중", icon="PAUSE")

        layout.separator()

        # ── 대화 메시지 표시 ──
        if len(scene.nup_messages) == 0:
            layout.label(text="모델링 요청을 입력하고 시작하세요", icon="INFO")
        else:
            messages = scene.nup_messages
            start = max(0, len(messages) - 30)

            for i in range(start, len(messages)):
                msg = messages[i]
                icon = AGENT_ICONS.get(msg.role, "DOT")
                status_icon = _get_status_icon(msg.content)
                expanded_key = f"nup_msg_expanded_{i}"
                is_expanded = scene.get(expanded_key, False)

                # 첫 줄 미리보기 (50자)
                first_line = msg.content.split("\n")[0][:50]
                if len(msg.content) > 50:
                    first_line += "..."

                # 접기/펼치기 헤더
                box = layout.box()
                row = box.row(align=True)
                toggle_icon = "TRIA_DOWN" if is_expanded else "TRIA_RIGHT"
                op = row.operator("nup.toggle_message", text="", icon=toggle_icon, emboss=False)
                op.index = i

                # 상태 아이콘 표시
                if status_icon:
                    row.label(text="", icon=status_icon)

                row.label(text=f"{msg.role}: {first_line}", icon=icon)

                # 복사 버튼
                copy_op = row.operator("nup.copy_log", text="", icon="COPYDOWN", emboss=False)
                copy_op.index = i

                # 펼쳐진 경우 전체 내용
                if is_expanded:
                    content_box = box.box()
                    lines = msg.content.split("\n")
                    for line in lines[:50]:
                        content_box.label(text=line[:100])
                    if len(lines) > 50:
                        content_box.label(text=f"... ({len(lines) - 50}줄 더)")

        # ── 대화형 수정 입력 ──
        layout.separator()
        box = layout.box()
        box.label(text="대화형 수정", icon="GREASEPENCIL")
        box.prop(scene, "nup_chat_input", text="")

        row = box.row(align=True)
        row.enabled = not scene.nup_is_running
        row.operator("nup.chat_dialog", text="입력 (한글)", icon="GREASEPENCIL")
        row.operator("nup.send_chat", text="전송", icon="PLAY")
