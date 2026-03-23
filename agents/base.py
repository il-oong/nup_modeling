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
                    "실제 표면 디테일을 코드로 구현해야 한다:\n"
                    "1. 표면 디테일: BMesh 정점을 수학 함수(sin/cos/noise)로 변형하여 울퉁불퉁한 질감 표현.\n"
                    "2. 엣지 플로우: 곡면 부위에 Edge Loop를 집중 배치.\n"
                    "3. 미세 굴곡: 정점마다 노이즈 오프셋을 적용하여 자연물의 비대칭/불규칙 표현.\n"
                    "4. 단면 변화: 각 세그먼트마다 반지름/형태를 다르게 하여 단조로움 방지.\n"
                    "5. 머티리얼: 셰이더 노드(Noise/Voronoi/ColorRamp)를 활용한 절차적 텍스처.\n"
                    "   - Bump/Normal 노드로 표면 미세 요철 표현.\n"
                    "   - 색상 변화(그라데이션, 얼룩, 반점)를 노드로 구현.\n"
                    "6. Displacement 모디파이어: Texture 기반 표면 변형 추가.\n"
                    "7. 디테일 파트 분리: 흠집, 주름, 이음새 등을 별도 지오메트리로 모델링.\n"
                    "8. 최소 segments=24, rings=16 이상 사용하여 곡면 해상도 확보.\n\n"
                    "금지: Subdivision만 올려서 매끈한 공 만들기. 반드시 실제 디테일이 있어야 한다."
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
