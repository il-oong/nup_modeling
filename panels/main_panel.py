"""메인 N-Panel UI"""

import bpy

# 스타일별 폴리곤 범위 참고 텍스트
POLY_RANGE = {
    "LOWPOLY": "권장: 100 ~ 5,000",
    "HIGHPOLY": "권장: 10,000 ~ 500,000",
}


class NUP_PT_MainPanel(bpy.types.Panel):
    bl_label = "NUP Modeling"
    bl_idname = "NUP_PT_MainPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "NUP Modeling"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # ── 스타일 설정 ──
        box = layout.box()
        box.label(text="스타일", icon="SHADING_SOLID")

        # 폴리곤 밀도 (로우폴리/하이폴리)
        row = box.row(align=True)
        row.prop(scene, "nup_output_style", expand=True)

        # 폴리곤 수 (스타일에 따라 범위 표시)
        col = box.column(align=True)
        col.prop(scene, "nup_output_max_polys")
        poly_hint = POLY_RANGE.get(scene.nup_output_style, "")
        if poly_hint:
            col.label(text=poly_hint, icon="INFO")

        box.separator()

        # 테마 (카툰/실사/게임에셋 등)
        box.label(text="테마", icon="BRUSH_DATA")
        box.prop(scene, "nup_output_theme", text="")

        # ── 용도 & 포맷 ──
        box = layout.box()
        box.label(text="출력", icon="OUTPUT")
        col = box.column(align=True)
        col.prop(scene, "nup_output_purpose")
        col.prop(scene, "nup_output_format")
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
        row = box.row(align=True)
        row.prop(scene, "nup_prompt", text="")
        row.operator("nup.paste_to_prompt", text="", icon="PASTEDOWN")

        row = box.row(align=True)
        if scene.nup_is_running:
            row.operator("nup.stop_chain", text="중단", icon="CANCEL")
            row.label(text=f"라운드 {scene.nup_current_round} 진행 중...")
        else:
            row.operator("nup.prompt_dialog", text="입력 (한글)", icon="GREASEPENCIL")
            row.operator("nup.run_chain", text="시작", icon="PLAY")

        # ── 상태 ──
        if scene.nup_current_round > 0:
            layout.label(text=f"라운드: {scene.nup_current_round}", icon="TIME")

        # ── 내보내기 ──
        layout.separator()
        row = layout.row(align=True)
        row.operator("nup.export_model", text="내보내기", icon="EXPORT")
        row.operator("nup.copy_code", text="코드 복사", icon="COPYDOWN")
