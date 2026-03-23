"""에이전트 대화 패널"""

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


class NUP_PT_ChatPanel(bpy.types.Panel):
    bl_label = "에이전트 대화"
    bl_idname = "NUP_PT_ChatPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "NUP Modeling"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # ── 대화 메시지 표시 ──
        box = layout.box()
        if len(scene.nup_messages) == 0:
            box.label(text="모델링 요청을 입력하고 시작하세요", icon="INFO")
        else:
            # 최근 20개 메시지만 표시 (UI 성능)
            messages = scene.nup_messages
            start = max(0, len(messages) - 20)
            for i in range(start, len(messages)):
                msg = messages[i]
                icon = AGENT_ICONS.get(msg.role, "DOT")

                msg_box = box.box()
                msg_box.label(text=f"{msg.role}:", icon=icon)

                # 긴 메시지는 줄여서 표시
                content = msg.content
                lines = content.split("\n")
                for line in lines[:10]:
                    if line.strip():
                        msg_box.label(text=line[:80])
                if len(lines) > 10:
                    msg_box.label(text=f"... ({len(lines) - 10}줄 더)")

        # ── 대화형 수정 입력 ──
        layout.separator()
        box = layout.box()
        box.label(text="대화형 수정", icon="GREASEPENCIL")
        box.prop(scene, "nup_chat_input", text="")

        row = box.row()
        row.enabled = not scene.nup_is_running
        row.operator("nup.send_chat", text="전송", icon="PLAY")
