"""에이전트 베이스 클래스"""

from ..core.gemini import call_gemini


class AgentBase:
    name: str = "Base"
    icon: str = ""
    system_prompt: str = ""

    def __init__(self, api_key: str, model: str = "gemini-3-flash-preview"):
        self.api_key = api_key
        self.model = model

    def build_system_prompt(self, output_settings: dict | None = None) -> str:
        """아웃풋 설정을 시스템 프롬프트에 주입한다."""
        prompt = self.system_prompt
        if output_settings:
            vfx = output_settings.get('vfx', [])
            vfx_text = ", ".join(vfx) if vfx else "없음"
            style = output_settings.get('style', 'N/A')
            settings_text = (
                f"\n\n[아웃풋 목표]\n"
                f"- 폴리곤: {style}\n"
                f"- 테마: {output_settings.get('theme', 'N/A')}\n"
                f"- 용도: {output_settings.get('purpose', 'N/A')}\n"
                f"- 최대 폴리곤 수: {output_settings.get('max_polys', 'N/A')}\n"
                f"- 내보내기 포맷: {output_settings.get('format', 'N/A')}\n"
                f"- 머티리얼: {'포함' if output_settings.get('material') else '미포함'}\n"
                f"- VFX: {vfx_text}"
            )
            prompt += settings_text

            # 스타일별 상세 지시
            if style == "HIGHPOLY":
                prompt += (
                    "\n\n[하이폴리 디테일 필수 요구사항]\n"
                    "하이폴리는 단순히 Subdivision으로 폴리곤 수만 늘리는 것이 아니다.\n"
                    "실제 표면 디테일 + PBR 머티리얼 + UV를 코드로 구현해야 한다.\n\n"
                    "=== 1. 메쉬 디테일 ===\n"
                    "- BMesh 정점을 수학 함수(sin/cos)로 변형하여 표면 질감 표현.\n"
                    "- 정점마다 노이즈 오프셋으로 자연물의 비대칭/불규칙 표현.\n"
                    "- 각 세그먼트마다 반지름/형태를 다르게 하여 단조로움 방지.\n"
                    "- 최소 segments=24, rings=16 이상으로 곡면 해상도 확보.\n"
                    "- 디테일 파트 분리: 흠집, 주름, 이음새 등 별도 지오메트리.\n\n"
                    "=== 2. PBR 머티리얼 (필수) ===\n"
                    "Principled BSDF 기반으로 다음 채널을 모두 설정:\n"
                    "- Base Color: Noise/Voronoi/ColorRamp로 절차적 색상 변화.\n"
                    "  단색 금지. 그라데이션, 얼룩, 반점 등 자연스러운 색 변화 필수.\n"
                    "- Roughness: 부위별 다른 거칠기 (Noise→ColorRamp→Roughness).\n"
                    "  예: 과일은 신선한 부분 0.2, 상처 부분 0.6.\n"
                    "- Normal/Bump: Noise/Voronoi→Bump 노드로 미세 요철 표현.\n"
                    "  표면의 질감(나무결, 피부결, 금속 스크래치 등)을 표현.\n"
                    "- Subsurface: 유기체(피부, 과일 등)는 SSS 적용.\n"
                    "- Metallic: 금속 재질은 1.0, 비금속은 0.0.\n"
                    "- Specular/Clearcoat: 광택 있는 표면(자동차, 과일)에 적용.\n\n"
                    "=== 3. UV 언랩 (필수) ===\n"
                    "- 오브젝트 생성 후 반드시 UV 전개 수행:\n"
                    "  bpy.ops.object.mode_set(mode='EDIT')\n"
                    "  bpy.ops.mesh.select_all(action='SELECT')\n"
                    "  bpy.ops.uv.smart_project(angle_limit=66, island_margin=0.02)\n"
                    "  bpy.ops.object.mode_set(mode='OBJECT')\n"
                    "- UV 좌표 기반 텍스처 매핑을 위해 TexCoord→Mapping 노드 사용.\n\n"
                    "=== 4. Displacement ===\n"
                    "- Texture 기반 Displacement 모디파이어로 표면 변형.\n"
                    "- 또는 셰이더 노드의 Displacement Output 활용.\n\n"
                    "금지: Subdivision만 올려서 매끈한 공 만들기.\n"
                    "금지: 단색 Principled BSDF만 달기. 반드시 노드 기반 절차적 텍스처."
                )
            elif style == "LOWPOLY":
                prompt += (
                    "\n\n[로우폴리 스타일 요구사항]\n"
                    "- 최소한의 폴리곤으로 형태의 특징을 잡는다.\n"
                    "- 6~8각 단면을 활용하여 각진 느낌을 살린다.\n"
                    "- Subdivision Surface 사용을 최소화한다.\n"
                    "- 머티리얼은 단순 색상 위주 (Flat Color)."
                )
        return prompt

    def run(self, messages: list[dict], output_settings: dict | None = None,
            image_path: str = "") -> str:
        """에이전트를 실행하여 응답을 반환한다."""
        system_prompt = self.build_system_prompt(output_settings)
        return call_gemini(self.api_key, system_prompt, messages,
                           model=self.model, image_path=image_path)
