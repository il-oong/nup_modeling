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

    unsplash_key: StringProperty(
        name="Unsplash Access Key",
        description="Unsplash API Access Key (unsplash.com/developers에서 발급)",
        subtype="PASSWORD",
        default="",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "api_key")
        layout.prop(self, "model_name")
        if not self.api_key:
            layout.label(text="API 키를 입력하세요", icon="ERROR")
        layout.separator()
        layout.prop(self, "unsplash_key")
        if not self.unsplash_key:
            layout.label(text="Unsplash 키 없이도 로컬 이미지 사용 가능", icon="INFO")


# ---------------------------------------------------------------------------
# Scene Properties (세션 데이터)
# ---------------------------------------------------------------------------
class NUPRefImageResult(bpy.types.PropertyGroup):
    """Unsplash 검색 결과 항목"""
    image_id: StringProperty(name="ID")
    url_thumb: StringProperty(name="Thumbnail URL")
    url_small: StringProperty(name="Small URL")
    url_regular: StringProperty(name="Regular URL")
    description: StringProperty(name="Description")
    author: StringProperty(name="Author")


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

    # 아웃풋 설정 - 스타일 (로우폴리/하이폴리)
    def _on_style_update(self, context):
        """스타일 변경 시 폴리곤 기본값 자동 변경"""
        scene = context.scene
        if scene.nup_output_style == "LOWPOLY":
            scene.nup_output_max_polys = 1000
        elif scene.nup_output_style == "HIGHPOLY":
            scene.nup_output_max_polys = 100000

    bpy.types.Scene.nup_output_style = EnumProperty(
        name="폴리곤",
        description="폴리곤 밀도",
        items=[
            ("LOWPOLY", "로우폴리", "Low polygon (100~5,000)"),
            ("HIGHPOLY", "하이폴리", "High polygon (10,000~500,000)"),
        ],
        default="LOWPOLY",
        update=_on_style_update,
    )
    bpy.types.Scene.nup_output_max_polys = IntProperty(
        name="Max Polygons",
        description="최대 폴리곤 수",
        default=1000,
        min=100,
        max=500000,
    )

    # 테마 (시각적 스타일)
    bpy.types.Scene.nup_output_theme = EnumProperty(
        name="테마",
        description="시각적 스타일",
        items=[
            ("CARTOON", "카툰", "Cartoon / Stylized"),
            ("REALISTIC", "실사", "Realistic / Photorealistic"),
            ("GAME_ASSET", "게임 에셋", "Game-ready asset"),
            ("ANIME", "애니메", "Anime style"),
            ("VOXEL", "복셀", "Voxel / Minecraft style"),
            ("FLAT", "플랫", "Flat / Minimal"),
        ],
        default="GAME_ASSET",
    )

    # VFX 옵션 (개별 체크박스)
    bpy.types.Scene.nup_vfx_enabled = BoolProperty(
        name="VFX 사용",
        description="VFX 이펙트를 모델에 추가합니다",
        default=False,
    )
    bpy.types.Scene.nup_vfx_particle = BoolProperty(
        name="파티클",
        description="파티클 시스템 (불, 연기, 불꽃, 비, 눈)",
        default=False,
    )
    bpy.types.Scene.nup_vfx_physics = BoolProperty(
        name="물리",
        description="물리 시뮬레이션 (천, 유체, 강체, 연체)",
        default=False,
    )
    bpy.types.Scene.nup_vfx_geonodes = BoolProperty(
        name="지오메트리 노드",
        description="Geometry Nodes 절차적 이펙트",
        default=False,
    )
    bpy.types.Scene.nup_vfx_compositing = BoolProperty(
        name="컴포지팅",
        description="컴포지팅 노드 (글로우, 블러, 색보정)",
        default=False,
    )
    bpy.types.Scene.nup_vfx_shader = BoolProperty(
        name="셰이더 이펙트",
        description="셰이더 노드 기반 이펙트 (홀로그램, 디졸브, 발광)",
        default=False,
    )
    bpy.types.Scene.nup_vfx_animation = BoolProperty(
        name="이펙트 애니메이션",
        description="키프레임 애니메이션 (폭발, 등장, 소멸)",
        default=False,
    )

    # 용도
    bpy.types.Scene.nup_output_purpose = EnumProperty(
        name="용도",
        items=[
            ("GAME", "게임", "Game engine (Unity/Unreal)"),
            ("RENDER", "렌더링", "Rendering / Illustration"),
            ("PRINT3D", "3D 프린팅", "3D printing"),
            ("ANIMATION", "애니메이션", "Animation / Rigging"),
            ("VIDEO", "영상", "Video / Motion graphics"),
        ],
        default="GAME",
    )

    # 내보내기 포맷
    bpy.types.Scene.nup_output_format = EnumProperty(
        name="포맷",
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
    bpy.types.Scene.nup_output_material = BoolProperty(
        name="Include Material",
        description="머티리얼 포함 여부",
        default=True,
    )

    # 참고 이미지
    bpy.types.Scene.nup_ref_image_path = StringProperty(
        name="참고 이미지",
        description="참고할 이미지 파일 경로",
        subtype="FILE_PATH",
        default="",
    )
    bpy.types.Scene.nup_ref_image_desc = StringProperty(
        name="이미지 설명",
        description="참고 이미지에 대한 추가 설명 (색감, 형태, 질감 등)",
        default="",
    )
    bpy.types.Scene.nup_ref_search_query = StringProperty(
        name="검색어",
        description="Unsplash 이미지 검색어",
        default="",
    )
    bpy.types.Scene.nup_ref_search_results = CollectionProperty(type=NUPRefImageResult)

    # 대화 메시지 & 코드 버전
    bpy.types.Scene.nup_messages = CollectionProperty(type=NUPMessageItem)
    bpy.types.Scene.nup_code_versions = CollectionProperty(type=NUPCodeVersion)
    bpy.types.Scene.nup_active_code_version = IntProperty(name="Active Version", default=0)


def unregister_properties():
    props = [
        "nup_prompt", "nup_chat_input", "nup_is_running",
        "nup_current_round", "nup_max_rounds", "nup_max_retries",
        "nup_output_style", "nup_output_theme",
        "nup_vfx_enabled", "nup_vfx_particle", "nup_vfx_physics",
        "nup_vfx_geonodes", "nup_vfx_compositing", "nup_vfx_shader",
        "nup_vfx_animation",
        "nup_output_purpose", "nup_output_format",
        "nup_output_max_polys", "nup_output_material",
        "nup_ref_image_path", "nup_ref_image_desc",
        "nup_ref_search_query", "nup_ref_search_results",
        "nup_messages", "nup_code_versions", "nup_active_code_version",
    ]
    for p in props:
        if hasattr(bpy.types.Scene, p):
            delattr(bpy.types.Scene, p)


# ---------------------------------------------------------------------------
# Register / Unregister
# ---------------------------------------------------------------------------
classes = [
    NUPRefImageResult,
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
