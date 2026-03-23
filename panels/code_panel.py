"""코드 표시 패널"""

import bpy
from ..operators.chain import get_chain_runner


class NUP_PT_CodePanel(bpy.types.Panel):
    bl_label = "코드"
    bl_idname = "NUP_PT_CodePanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "NUP Modeling"
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # ── 코드 버전 선택 ──
        if len(scene.nup_code_versions) > 0:
            box = layout.box()
            box.label(text="코드 버전", icon="LINENUMBERS_ON")

            row = box.row(align=True)
            for cv in scene.nup_code_versions:
                is_active = cv.version == scene.nup_active_code_version
                if is_active:
                    row.label(text=f"[v{cv.version}]")
                else:
                    row.label(text=f"v{cv.version}")

            # 현재 코드 표시
            runner = get_chain_runner()
            if runner and runner.latest_code:
                code_box = box.box()
                lines = runner.latest_code.split("\n")
                for line in lines[:30]:
                    code_box.label(text=line[:90])
                if len(lines) > 30:
                    code_box.label(text=f"... ({len(lines) - 30}줄 더)")

            # 버튼
            row = box.row(align=True)
            row.operator("nup.copy_code", text="복사", icon="COPYDOWN")
            row.operator("nup.export_model", text="내보내기", icon="EXPORT")
        else:
            layout.label(text="아직 생성된 코드가 없습니다", icon="INFO")
