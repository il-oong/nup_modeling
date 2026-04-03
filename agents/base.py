"""에이전트 베이스 클래스"""

from ..core.gemini import call_gemini


# 폴리곤 수에 따른 디테일 레벨 매핑
def _poly_detail_guide(max_polys: int) -> str:
    """폴리곤 수에 따라 구체적인 메쉬 세그먼트/디테일 가이드를 반환한다."""
    if max_polys <= 300:
        return (
            "\n\n[디테일 가이드 - 극저폴리 (~300)]\n"
            "- 원형 단면: segments=6~8\n"
            "- 구체: segments=8, rings=5\n"
            "- 파트별 최소 면 사용. 각진 실루엣.\n"
            "- 폴리곤 예산을 최대한 활용하되 300개를 넘지 않는다.\n"
            "- Subdivision Surface 금지."
        )
    elif max_polys <= 700:
        return (
            "\n\n[디테일 가이드 - 저폴리 (~700)]\n"
            "- 원형 단면: segments=10~12\n"
            "- 구체: segments=12, rings=8\n"
            "- 메인 파트 + 서브파트 2~3개까지 충분히 표현.\n"
            "- 700개 폴리곤 예산을 최대한 활용한다.\n"
            "- Subdivision Surface 레벨 1 허용."
        )
    elif max_polys <= 1500:
        return (
            "\n\n[디테일 가이드 - 표준 로우폴리 (~1500)]\n"
            "- 원형 단면: segments=12~16\n"
            "- 구체: segments=16, rings=10\n"
            "- 몸통/머리/다리 등 주요 파트를 모두 충분한 폴리곤으로 표현.\n"
            "- 각 파트에 넉넉한 폴리곤 배분. 폴리곤 예산을 80% 이상 활용한다.\n"
            "- BMesh 경로 기반 튜브 또는 정점 변형으로 유기적 실루엣 구현.\n"
            "- Subdivision Surface 레벨 1 적극 활용.\n"
            "- Edge Loop으로 형태 디테일 강조."
        )
    elif max_polys <= 3000:
        return (
            "\n\n[디테일 가이드 - 고품질 로우폴리 (~3000)]\n"
            "- 원형 단면: segments=16~20\n"
            "- 구체: segments=20, rings=12\n"
            "- 세부 파트 풍부하게 표현 (손가락, 발가락, 귀, 꼬리 등).\n"
            "- 폴리곤 예산을 80% 이상 활용. 매끄러운 곡면 표현.\n"
            "- Subdivision Surface 레벨 1~2 허용.\n"
            "- BMesh 정점 변형으로 미세한 실루엣 조정."
        )
    else:  # 3001~5000
        return (
            "\n\n[디테일 가이드 - 디테일 로우폴리 (~5000)]\n"
            "- 원형 단면: segments=20~24\n"
            "- 구체: segments=24, rings=14\n"
            "- 모든 파트를 충분한 디테일로 표현.\n"
            "- 폴리곤 예산을 80% 이상 활용.\n"
            "- Subdivision Surface 레벨 1~2.\n"
            "- BMesh 정점 변형으로 스컬핑 효과 가능.\n"
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
                f"- 폴리곤 예산: {max_polys}개 (80% 이상 활용할 것)\n"
                f"- 내보내기 포맷: {output_settings.get('format', 'N/A')}\n"
                f"- 머티리얼: {'포함' if output_settings.get('material') else '미포함'}\n"
                f"- VFX: {vfx_text}"
            )
            prompt += settings_text

            # 로우폴리 기본 요구사항
            prompt += (
                "\n\n[로우폴리 스타일 핵심 원칙]\n"
                f"- 폴리곤 예산 {max_polys}개를 최대한 활용한다. 너무 적게 쓰면 품질이 떨어진다.\n"
                "- 로우폴리 = '적은 폴리곤으로 멋진 형태'이지 '깨진 형태'가 아니다.\n"
                "- 각 파트에 충분한 segments를 사용하여 형태가 명확해야 한다.\n"
                "- 유기체(동물, 사람)는 BMesh 경로 기반 튜브 또는 정점 변형으로 자연스러운 실루엣을 만든다.\n"
                "- 단순 원통/구체/큐브 나열 금지. 파트 간 자연스러운 연결 필수.\n"
                "- Flat Color 머티리얼 사용. 파트별 다른 색상으로 시각적 구분."
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
