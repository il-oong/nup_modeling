"""메인 N-Panel UI"""

import bpy


class NUP_PT_MainPanel(bpy.types.Panel):
    bl_label = "NUP Modeling"
    bl_idname = "NUP_PT_MainPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "NUP Modeling"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # ── 아웃풋 설정 ──
        box = layout.box()
        box.label(text="아웃풋 설정", icon="OUTPUT")
        col = box.column(align=True)
        col.prop(scene, "nup_output_style")
        col.prop(scene, "nup_output_purpose")
        col.prop(scene, "nup_output_format")
        col.prop(scene, "nup_output_max_polys")
        col.prop(scene, "nup_output_material")

        layout.separator()

        # ── 체인 설정 ──
        box = layout.box()
        box.label(text="체인 설정", icon="LINKED")
        col = box.column(align=True)
        col.prop(scene, "nup_max_rounds")
        col.prop(scene, "nup_max_retries")

        layout.separator()

        # ── 요청 입력 ──
        box = layout.box()
        box.label(text="모델링 요청", icon="OUTLINER_OB_MESH")
        box.prop(scene, "nup_prompt", text="")

        row = box.row(align=True)
        if scene.nup_is_running:
            row.operator("nup.stop_chain", text="중단", icon="CANCEL")
            row.label(text=f"라운드 {scene.nup_current_round} 진행 중...")
        else:
            row.operator("nup.run_chain", text="시작", icon="PLAY")

        # ── 상태 ──
        if scene.nup_current_round > 0:
            layout.label(text=f"라운드: {scene.nup_current_round}", icon="TIME")

        # ── 내보내기 ──
        layout.separator()
        row = layout.row(align=True)
        row.operator("nup.export_model", text="내보내기", icon="EXPORT")
        row.operator("nup.copy_code", text="코드 복사", icon="COPYDOWN")
