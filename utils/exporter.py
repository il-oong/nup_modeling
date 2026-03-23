"""포맷별 내보내기 유틸리티"""


def get_export_extension(fmt: str) -> str:
    """포맷 코드에 대한 파일 확장자를 반환한다."""
    extensions = {
        "BLEND": ".blend",
        "FBX": ".fbx",
        "OBJ": ".obj",
        "STL": ".stl",
        "GLTF": ".glb",
    }
    return extensions.get(fmt, ".blend")
