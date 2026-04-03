"""메인 N-Panel UI - 로우폴리 전용"""

import bpy

# 에이전트별 평균 소요 시간 (초)
_AGENT_TIME = {
    "prompter": 8,
    "architect": 12,
    "coder": 18,
    "tester": 12,
    "reviewer": 12,
    "optimizer": 15,
    "vfx": 20,
    "retry": 25,
    "exec": 5,
}


def _estimate_time(scene):
    """설정 기반 예상 제작 시간을 문자열로 반환한다."""
    base = (
        _AGENT_TIME["prompter"]
        + _AGENT_TIME["architect"]
        + _AGENT_TIME["coder"]
        + _AGENT_TIME["tester"]
        + _AGENT_TIME["reviewer"]
        + _AGENT_TIME["optimizer"]
        + _AGENT_TIME["exec"]
    )

    # VFX 활성화 시 추가
    vfx_count = 0
    if scene.nup_vfx_enabled:
        for attr in ("nup_vfx_particle", "nup_vfx_physics", "nup_vfx_geonodes",
                      "nup_vfx_compositing", "nup_vfx_shader", "nup_vfx_animation"):
            if getattr(scene, attr, False):
                vfx_count += 1
        if vfx_count > 0:
            base += _AGENT_TIME["vfx"] + _AGENT_TIME["tester"]

    retries = scene.nup_max_retries
    retry_time = _AGENT_TIME["retry"] * retries

    if getattr(scene, "nup_ref_image_path", ""):
        base += 10

    total_min = base // 60
    total_max = (base + retry_time) // 60

    if total_min < 1:
        total_min = 1
    if total_max < 1:
        total_max = 1

    if total_min == total_max:
        return f"약 {total_min}분"
    return f"약 {total_min}~{total_max}분"


class NUP_PT_MainPanel(bpy.types.Panel):
    bl_label = "NUP Modeling (로우폴리)"
    bl_idname = "NUP_PT_MainPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "NUP Modeling"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # ── 로우폴리 설정 ──
        box = layout.box()
        box.label(text="로우폴리 설정", icon="MESH_ICOSPHERE")

        # 폴리곤 수 슬라이더
        col = box.column(align=True)
        col.prop(scene, "nup_output_max_polys", slider=True)
        col.label(text="범위: 50 ~ 5,000", icon="INFO")

        box.separator()

        # 테마
        box.label(text="테마", icon="BRUSH_DATA")
        box.prop(scene, "nup_output_theme", text="")

        # ── VFX ──
        box = layout.box()
        row = box.row()
        row.prop(scene, "nup_vfx_enabled", text="VFX 이펙트", icon="PARTICLES")
        if scene.nup_vfx_enabled:
            col = box.column(align=True)
            col.prop(scene, "nup_vfx_particle", icon="FORCE_WIND")
            col.prop(scene, "nup_vfx_physics", icon="PHYSICS")
            col.prop(scene, "nup_vfx_geonodes", icon="GEOMETRY_NODES")
            col.prop(scene, "nup_vfx_compositing", icon="NODE_COMPOSITING")
            col.prop(scene, "nup_vfx_shader", icon="SHADING_RENDERED")
            col.prop(scene, "nup_vfx_animation", icon="RENDER_ANIMATION")

        layout.separator()

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
        col.prop(scene, "nup_live_preview", icon="PLAY")

        layout.separator()

        # ── 참고 이미지 ──
        box = layout.box()
        box.label(text="참고 이미지", icon="IMAGE_DATA")

        box.prop(scene, "nup_ref_image_path", text="파일")

        row = box.row(align=True)
        row.prop(scene, "nup_ref_search_query", text="")
        row.operator("nup.search_ref_image", text="", icon="VIEWZOOM")

        if scene.nup_ref_image_path:
            row = box.row(align=True)
            row.label(text=scene.nup_ref_image_path.split("\\")[-1].split("/")[-1], icon="CHECKMARK")
            row.operator("nup.clear_ref_image", text="", icon="X")

        results = scene.nup_ref_search_results
        if results:
            box.separator()
            box.label(text=f"검색 결과: {len(results)}개", icon="VIEWZOOM")
            grid = box.grid_flow(row_major=True, columns=3, even_columns=True, even_rows=True)
            for i, item in enumerate(results):
                item_box = grid.box()
                col = item_box.column(align=True)

                thumb_name = f"nup_thumb_{item.image_id}"
                thumb_img = bpy.data.images.get(thumb_name)
                icon_id = 0
                if thumb_img:
                    if thumb_img.preview is None:
                        thumb_img.preview_ensure()
                    if thumb_img.preview:
                        icon_id = thumb_img.preview.icon_id

                if icon_id > 0:
                    col.template_icon(icon_value=icon_id, scale=5.0)
                else:
                    sub = col.box()
                    sub.scale_y = 3.0
                    sub.label(text="...", icon="IMAGE_DATA")

                desc = item.description[:25] if item.description else f"#{i+1}"
                col.label(text=desc)
                op = col.operator("nup.select_ref_image", text="선택", icon="CHECKMARK")
                op.index = i

        box.prop(scene, "nup_ref_image_desc", text="설명")

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

        # ── 예상 제작 시간 ──
        est = _estimate_time(scene)
        box.label(text=f"예상 시간: {est}", icon="TIME")

        # ── 상태 ──
        if scene.nup_current_round > 0:
            layout.label(text=f"라운드: {scene.nup_current_round}", icon="TIME")

        # ── 내보내기 ──
        layout.separator()
        row = layout.row(align=True)
        row.operator("nup.export_model", text="내보내기", icon="EXPORT")
        row.operator("nup.copy_code", text="코드 복사", icon="COPYDOWN")
