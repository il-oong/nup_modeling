"""에이전트 베이스 클래스"""

from ..core.gemini import call_gemini


# 폴리곤 수에 따른 디테일 레벨 매핑
def _poly_detail_guide(max_polys: int) -> str:
    """폴리곤 수에 따라 구체적인 메쉬 세그먼트/디테일 가이드를 반환한다."""
    if max_polys <= 200:
        return (
            "\n\n[폴리곤 디테일 가이드 - 극저폴리 (~200)]\n"
            "- 원형 단면: 4~6각형 (segments=4~6)\n"
            "- 구체: segments=4, rings=3 수준\n"
            "- 파트별 최소 면만 사용. 박스 형태 위주.\n"
            "- 디테일은 실루엣으로만 표현, 곡면 없음.\n"
            "- Subdivision Surface 절대 금지."
        )
    elif max_polys <= 500:
        return (
            "\n\n[폴리곤 디테일 가이드 - 초저폴리 (~500)]\n"
            "- 원형 단면: 6~8각형 (segments=6~8)\n"
            "- 구체: segments=8, rings=4 수준\n"
            "- 주요 형태만 표현. 세부 파트는 단순 박스/원뿔.\n"
            "- Subdivision Surface 금지."
        )
    elif max_polys <= 1000:
        return (
            "\n\n[폴리곤 디테일 가이드 - 로우폴리 기본 (~1000)]\n"
            "- 원형 단면: 8~10각형 (segments=8~10)\n"
            "- 구체: segments=10, rings=6 수준\n"
            "- 메인 파트 + 2~3개 서브파트까지 표현 가능.\n"
            "- 부드러운 곡면은 Shade Smooth로만 처리.\n"
            "- Subdivision Surface 레벨 최대 1."
        )
    elif max_polys <= 2000:
        return (
            "\n\n[폴리곤 디테일 가이드 - 로우폴리 중간 (~2000)]\n"
            "- 원형 단면: 10~12각형 (segments=10~12)\n"
            "- 구체: segments=12, rings=8 수준\n"
            "- 파트별 디테일 약간 추가 가능 (눈, 입 등 표정).\n"
            "- 주요 곡면에 한해 Subdivision Surface 레벨 1.\n"
            "- Edge Loop 2~3개로 형태 강조 가능."
        )
    else:  # 2001~5000
        return (
            "\n\n[폴리곤 디테일 가이드 - 로우폴리 고밀도 (~5000)]\n"
            "- 원형 단면: 12~16각형 (segments=12~16)\n"
            "- 구체: segments=16, rings=10 수준\n"
            "- 세부 파트 표현 가능 (손가락, 발가락, 귀 등).\n"
            "- Subdivision Surface 레벨 1 허용.\n"
            "- BMesh 정점 변형으로 미세한 실루엣 조정 가능.\n"
            "- Edge Crease/Bevel로 엣지 강조."
        )


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
            max_polys = output_settings.get('max_polys', 1000)
            settings_text = (
                f"\n\n[아웃풋 목표]\n"
                f"- 스타일: 로우폴리\n"
                f"- 테마: {output_settings.get('theme', 'N/A')}\n"
                f"- 용도: {output_settings.get('purpose', 'N/A')}\n"
                f"- 최대 폴리곤 수: {max_polys}\n"
                f"- 내보내기 포맷: {output_settings.get('format', 'N/A')}\n"
                f"- 머티리얼: {'포함' if output_settings.get('material') else '미포함'}\n"
                f"- VFX: {vfx_text}"
            )
            prompt += settings_text

            # 로우폴리 기본 요구사항
            prompt += (
                "\n\n[로우폴리 스타일 필수 요구사항]\n"
                "- 최소한의 폴리곤으로 형태의 특징을 잡는다.\n"
                "- 각진 느낌을 살리되, 실루엣은 명확하게.\n"
                "- 머티리얼은 단순 색상 위주 (Flat Color).\n"
                "- 불필요한 Subdivision Surface 사용을 최소화한다.\n"
                f"- 반드시 최대 {max_polys}개 폴리곤 이내로 제작한다."
            )

            # 폴리곤 수에 따른 구체적 디테일 가이드
            prompt += _poly_detail_guide(max_polys)

        return prompt

    def run(self, messages: list[dict], output_settings: dict | None = None,
            image_path: str = "") -> str:
        """에이전트를 실행하여 응답을 반환한다."""
        system_prompt = self.build_system_prompt(output_settings)
        return call_gemini(self.api_key, system_prompt, messages,
                           model=self.model, image_path=image_path)
