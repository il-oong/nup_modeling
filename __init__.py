bl_info = {
    "name": "NUP Modeling",
    "author": "il-oong",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > NUP Modeling",
    "description": "AI 에이전트 체인으로 Blender 3D 모델링 코드를 자동 생성",
    "category": "3D View",
}

import bpy
from bpy.props import (
    StringProperty,
    IntProperty,
    EnumProperty,
    CollectionProperty,
    BoolProperty,
)

from . import operators
from . import panels


# ---------------------------------------------------------------------------
# Addon Preferences (API 키 저장)
# ---------------------------------------------------------------------------
class NUPModelingPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    api_key: StringProperty(
        name="Google API Key",
        description="Google Gemini API 키",
        subtype="PASSWORD",
        default="",
    )

    model_name: StringProperty(
        name="Model",
        description="Gemini 모델명 (예: gemini-3-flash-preview)",
        default="gemini-3-flash-preview",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "api_key")
        layout.prop(self, "model_name")
        if not self.api_key:
            layout.label(text="API 키를 입력하세요", icon="ERROR")


# ---------------------------------------------------------------------------
# Scene Properties (세션 데이터)
# ---------------------------------------------------------------------------
class NUPMessageItem(bpy.types.PropertyGroup):
    role: StringProperty(name="Role")        # architect, coder, tester, reviewer, optimizer, user
    content: StringProperty(name="Content")
    is_code: BoolProperty(name="Is Code", default=False)


class NUPCodeVersion(bpy.types.PropertyGroup):
    version: IntProperty(name="Version")
    code: StringProperty(name="Code")
    status: StringProperty(name="Status")    # success, error


def register_properties():
    bpy.types.Scene.nup_prompt = StringProperty(
        name="Prompt",
        description="모델링 요청을 입력하세요",
        default="",
    )
    bpy.types.Scene.nup_chat_input = StringProperty(
        name="Chat",
        description="대화형 수정 요청",
        default="",
    )
    bpy.types.Scene.nup_is_running = BoolProperty(
        name="Running",
        default=False,
    )
    bpy.types.Scene.nup_current_round = IntProperty(
        name="Current Round",
        default=0,
    )
    bpy.types.Scene.nup_max_rounds = IntProperty(
        name="Max Rounds",
        description="최대 라운드 수",
        default=3,
        min=1,
        max=10,
    )
    bpy.types.Scene.nup_max_retries = IntProperty(
        name="Max Retries",
        description="Tester 실패 시 최대 재시도 횟수",
        default=3,
        min=1,
        max=5,
    )

    # 아웃풋 설정
    bpy.types.Scene.nup_output_style = EnumProperty(
        name="Style",
        items=[
            ("LOWPOLY", "로우폴리", "Low polygon style"),
            ("HIGHPOLY", "하이폴리", "High polygon detailed"),
            ("CARTOON", "카툰", "Cartoon/stylized"),
            ("REALISTIC", "리얼리스틱", "Realistic style"),
        ],
        default="LOWPOLY",
    )
    bpy.types.Scene.nup_output_purpose = EnumProperty(
        name="Purpose",
        items=[
            ("GAME", "게임 에셋", "Game asset"),
            ("RENDER", "렌더링", "Rendering"),
            ("PRINT3D", "3D 프린팅", "3D printing"),
            ("ANIMATION", "애니메이션", "Animation"),
            ("VIDEO", "영상", "Video / motion graphics"),
        ],
        default="GAME",
    )
    bpy.types.Scene.nup_output_format = EnumProperty(
        name="Format",
        items=[
            ("BLEND", ".blend", "Blender file"),
            ("FBX", ".fbx", "FBX format"),
            ("OBJ", ".obj", "OBJ format"),
            ("STL", ".stl", "STL format"),
            ("GLTF", ".glTF", "glTF format"),
            ("MP4", ".mp4", "MP4 video"),
        ],
        default="FBX",
    )
    bpy.types.Scene.nup_output_max_polys = IntProperty(
        name="Max Polygons",
        description="최대 폴리곤 수 (0 = 제한 없음)",
        default=10000,
        min=0,
    )
    bpy.types.Scene.nup_output_material = BoolProperty(
        name="Include Material",
        description="머티리얼 포함 여부",
        default=True,
    )

    # 대화 메시지 & 코드 버전
    bpy.types.Scene.nup_messages = CollectionProperty(type=NUPMessageItem)
    bpy.types.Scene.nup_code_versions = CollectionProperty(type=NUPCodeVersion)
    bpy.types.Scene.nup_active_code_version = IntProperty(name="Active Version", default=0)


def unregister_properties():
    props = [
        "nup_prompt", "nup_chat_input", "nup_is_running",
        "nup_current_round", "nup_max_rounds", "nup_max_retries",
        "nup_output_style", "nup_output_purpose", "nup_output_format",
        "nup_output_max_polys", "nup_output_material",
        "nup_messages", "nup_code_versions", "nup_active_code_version",
    ]
    for p in props:
        if hasattr(bpy.types.Scene, p):
            delattr(bpy.types.Scene, p)


# ---------------------------------------------------------------------------
# Register / Unregister
# ---------------------------------------------------------------------------
classes = [
    NUPMessageItem,
    NUPCodeVersion,
    NUPModelingPreferences,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    operators.register()
    panels.register()
    register_properties()


def unregister():
    unregister_properties()
    panels.unregister()
    operators.unregister()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
