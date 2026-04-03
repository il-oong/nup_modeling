"""에이전트 대화 패널 - 실시간 대화 표시 (기본 열림)"""

import bpy

# 에이전트별 아이콘 매핑
AGENT_ICONS = {
    "Prompter": "GREASEPENCIL",
    "Architect": "CONSTRAINT",
    "Coder": "TEXT",
    "Tester": "CHECKMARK",
    "Reviewer": "VIEWZOOM",
    "Optimizer": "MODIFIER",
    "VFX": "PARTICLES",
    "User": "USER",
    "System": "ERROR",
}

# 에이전트별 색상 설명 (UI 헤더 표시용)
AGENT_LABELS = {
    "Prompter": "프롬프터",
    "Architect": "설계자",
    "Coder": "코더",
    "Tester": "테스터",
    "Reviewer": "리뷰어",
    "Optimizer": "최적화",
    "VFX": "VFX",
    "User": "사용자",
    "System": "시스템",
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
    elif "[BLOCKED]" in content:
        return "CANCEL"
    elif "[WARNING]" in content:
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
    # 기본 열림 상태로 변경 - 실시간 대화 확인용
    bl_options = set()

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # 상단 버튼
        row = layout.row(align=True)
        op = row.operator("nup.copy_log", text="전체 로그 복사", icon="COPYDOWN")
        op.index = -1
        row.operator("nup.clear_messages", text="초기화", icon="TRASH")

        layout.separator()

        # ── 진행 상태 표시 (실시간) ──
        if scene.nup_is_running:
            status_box = layout.box()
            status_box.label(text="에이전트 체인 진행 중...", icon="SORTTIME")

            # 현재 진행 중인 에이전트 표시
            if len(scene.nup_messages) > 0:
                last_msg = scene.nup_messages[-1]
                agent_label = AGENT_LABELS.get(last_msg.role, last_msg.role)
                agent_icon = AGENT_ICONS.get(last_msg.role, "DOT")
                status_box.label(text=f"현재: {agent_label}", icon=agent_icon)

            layout.separator()

        # ── 결과 상태 요약 ──
        if len(scene.nup_messages) > 0 and not scene.nup_is_running:
            status_box = layout.box()
            row = status_box.row()

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
            elif "[FAIL]" in last_test or "[BLOCKED]" in last_test:
                row.label(text="상태: 실패", icon="CANCEL")
                if "안전성" in last_test:
                    status_box.label(text="원인: 안전하지 않은 코드")
                elif "문법 오류" in last_test:
                    status_box.label(text="원인: Python 문법 오류")
                else:
                    status_box.label(text="원인: 코드 오류")
            elif last_code_exists:
                row.label(text="상태: 코드 생성됨", icon="FILE_SCRIPT")
            else:
                row.label(text="상태: 대기 중", icon="PAUSE")

        layout.separator()

        # ── 에이전트 대화 메시지 (실시간 표시) ──
        if len(scene.nup_messages) == 0:
            layout.label(text="모델링 요청을 입력하고 시작하세요", icon="INFO")
        else:
            messages = scene.nup_messages
            start = max(0, len(messages) - 50)  # 최근 50개까지 표시

            # 라운드 구분 표시
            current_agent = None
            for i in range(start, len(messages)):
                msg = messages[i]
                icon = AGENT_ICONS.get(msg.role, "DOT")
                status_icon = _get_status_icon(msg.content)
                expanded_key = f"nup_msg_expanded_{i}"

                # 진행 중일 때 최신 메시지는 자동 펼침
                is_latest = (i == len(messages) - 1)
                is_expanded = scene.get(expanded_key, is_latest and scene.nup_is_running)

                # 에이전트 변경 시 구분선
                if msg.role != current_agent and msg.role != "System":
                    current_agent = msg.role
                    agent_label = AGENT_LABELS.get(msg.role, msg.role)

                # 첫 줄 미리보기 (80자)
                first_line = msg.content.split("\n")[0][:80]
                if len(msg.content) > 80:
                    first_line += "..."

                # 접기/펼치기 헤더
                box = layout.box()
                row = box.row(align=True)
                toggle_icon = "TRIA_DOWN" if is_expanded else "TRIA_RIGHT"
                op = row.operator("nup.toggle_message", text="", icon=toggle_icon, emboss=False)
                op.index = i

                # 상태 아이콘
                if status_icon:
                    row.label(text="", icon=status_icon)

                # 에이전트명 (한글) + 미리보기
                agent_label = AGENT_LABELS.get(msg.role, msg.role)
                row.label(text=f"[{agent_label}] {first_line}", icon=icon)

                # 복사 버튼
                copy_op = row.operator("nup.copy_log", text="", icon="COPYDOWN", emboss=False)
                copy_op.index = i

                # 펼쳐진 경우 전체 내용
                if is_expanded:
                    content_box = box.box()
                    lines = msg.content.split("\n")
                    for line in lines[:80]:
                        content_box.label(text=line[:120])
                    if len(lines) > 80:
                        content_box.label(text=f"... ({len(lines) - 80}줄 더)")

        # ── 대화형 수정 입력 ──
        layout.separator()
        box = layout.box()
        box.label(text="대화형 수정", icon="GREASEPENCIL")
        row = box.row(align=True)
        row.prop(scene, "nup_chat_input", text="")
        row.operator("nup.paste_to_chat", text="", icon="PASTEDOWN")

        row = box.row(align=True)
        row.enabled = not scene.nup_is_running
        row.operator("nup.chat_dialog", text="입력 (한글)", icon="GREASEPENCIL")
        row.operator("nup.send_chat", text="전송", icon="PLAY")
