"""에이전트 대화 패널 - 접기/펼치기 지원"""

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


class NUP_OT_ToggleMessage(bpy.types.Operator):
    bl_idname = "nup.toggle_message"
    bl_label = "메시지 토글"
    bl_description = "메시지 상세 보기"

    index: bpy.props.IntProperty()

    def execute(self, context):
        scene = context.scene
        # 토글 상태를 scene에 저장
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

        if len(scene.nup_messages) == 0:
            layout.label(text="모델링 요청을 입력하고 시작하세요", icon="INFO")
        else:
            messages = scene.nup_messages
            # 최근 30개만 표시
            start = max(0, len(messages) - 30)

            for i in range(start, len(messages)):
                msg = messages[i]
                icon = AGENT_ICONS.get(msg.role, "DOT")
                expanded_key = f"nup_msg_expanded_{i}"
                is_expanded = scene.get(expanded_key, False)

                # 첫 줄 미리보기 (40자)
                first_line = msg.content.split("\n")[0][:40]
                if len(msg.content) > 40:
                    first_line += "..."

                # 접기/펼치기 헤더
                box = layout.box()
                row = box.row(align=True)
                toggle_icon = "TRIA_DOWN" if is_expanded else "TRIA_RIGHT"
                op = row.operator("nup.toggle_message", text="", icon=toggle_icon, emboss=False)
                op.index = i
                row.label(text=f"{msg.role}: {first_line}", icon=icon)

                # 펼쳐진 경우 전체 내용
                if is_expanded:
                    content_box = box.box()
                    lines = msg.content.split("\n")
                    for line in lines[:50]:
                        content_box.label(text=line[:100])
                    if len(lines) > 50:
                        content_box.label(text=f"... ({len(lines) - 50}줄 더)")

        # 진행 중 표시
        if scene.nup_is_running:
            layout.label(text="에이전트 진행 중...", icon="SORTTIME")

        # 대화형 수정 입력
        layout.separator()
        box = layout.box()
        box.label(text="대화형 수정", icon="GREASEPENCIL")
        box.prop(scene, "nup_chat_input", text="")

        row = box.row(align=True)
        row.enabled = not scene.nup_is_running
        row.operator("nup.chat_dialog", text="입력 (한글)", icon="GREASEPENCIL")
        row.operator("nup.send_chat", text="전송", icon="PLAY")
