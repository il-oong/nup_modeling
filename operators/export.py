"""내보내기 및 코드 복사 오퍼레이터"""

import bpy

from .chain import get_chain_runner


class NUP_OT_ExportModel(bpy.types.Operator):
    bl_idname = "nup.export_model"
    bl_label = "내보내기"
    bl_description = "모델을 지정된 포맷으로 내보냅니다"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(
        default="*.fbx;*.obj;*.stl;*.glb;*.blend;*.mp4",
        options={"HIDDEN"},
    )

    def execute(self, context):
        scene = context.scene
        fmt = scene.nup_output_format

        # 선택된 오브젝트가 없으면 전체 선택
        if not context.selected_objects:
            bpy.ops.object.select_all(action="SELECT")

        filepath = self.filepath
        if not filepath:
            filepath = "//nup_model"

        try:
            if fmt == "FBX":
                bpy.ops.export_scene.fbx(filepath=filepath + ".fbx", use_selection=True)
            elif fmt == "OBJ":
                # Blender 3.6+ 새 API, fallback 포함
                try:
                    bpy.ops.wm.obj_export(filepath=filepath + ".obj", export_selected_objects=True)
                except AttributeError:
                    bpy.ops.export_scene.obj(filepath=filepath + ".obj", use_selection=True)
            elif fmt == "STL":
                bpy.ops.export_mesh.stl(filepath=filepath + ".stl", use_selection=True)
            elif fmt == "GLTF":
                # glTF 파라미터명 호환
                try:
                    bpy.ops.export_scene.gltf(filepath=filepath + ".glb", use_selection=True)
                except TypeError:
                    bpy.ops.export_scene.gltf(filepath=filepath + ".glb", export_selected=True)
            elif fmt == "BLEND":
                bpy.ops.wm.save_as_mainfile(filepath=filepath + ".blend")
            elif fmt == "MP4":
                scene.render.filepath = filepath
                scene.render.image_settings.file_format = "FFMPEG"
                scene.render.ffmpeg.format = "MPEG4"
                scene.render.ffmpeg.codec = "H264"
                bpy.ops.render.render(animation=True)

            self.report({"INFO"}, f"{fmt} 내보내기 완료")
        except Exception as e:
            self.report({"ERROR"}, f"내보내기 실패: {e}")

        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class NUP_OT_CopyCode(bpy.types.Operator):
    bl_idname = "nup.copy_code"
    bl_label = "코드 복사"
    bl_description = "현재 코드를 클립보드에 복사합니다"

    def execute(self, context):
        runner = get_chain_runner()
        if runner and runner.latest_code:
            context.window_manager.clipboard = runner.latest_code
            self.report({"INFO"}, "코드가 클립보드에 복사되었습니다")
        else:
            self.report({"WARNING"}, "복사할 코드가 없습니다")
        return {"FINISHED"}
