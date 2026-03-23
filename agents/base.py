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
            settings_text = (
                f"\n\n[아웃풋 목표]\n"
                f"- 폴리곤: {output_settings.get('style', 'N/A')}\n"
                f"- 테마: {output_settings.get('theme', 'N/A')}\n"
                f"- 용도: {output_settings.get('purpose', 'N/A')}\n"
                f"- 최대 폴리곤 수: {output_settings.get('max_polys', 'N/A')}\n"
                f"- 내보내기 포맷: {output_settings.get('format', 'N/A')}\n"
                f"- 머티리얼: {'포함' if output_settings.get('material') else '미포함'}"
            )
            prompt += settings_text
        return prompt

    def run(self, messages: list[dict], output_settings: dict | None = None) -> str:
        """에이전트를 실행하여 응답을 반환한다."""
        system_prompt = self.build_system_prompt(output_settings)
        return call_gemini(self.api_key, system_prompt, messages, model=self.model)
