"""에이전트 체인 루프 관리"""

from ..agents import (
    ArchitectAgent,
    CoderAgent,
    TesterAgent,
    ReviewerAgent,
    OptimizerAgent,
)
from ..agents.tester import TesterAgent as TesterCls


class ChainRunner:
    """에이전트 체인을 순서대로 실행한다."""

    def __init__(self, api_key: str, output_settings: dict):
        self.api_key = api_key
        self.output_settings = output_settings
        self.architect = ArchitectAgent(api_key)
        self.coder = CoderAgent(api_key)
        self.tester = TesterAgent(api_key)
        self.reviewer = ReviewerAgent(api_key)
        self.optimizer = OptimizerAgent(api_key)

        self.messages: list[dict] = []     # 전체 대화 히스토리
        self.log: list[dict] = []          # UI 표시용 로그
        self.code_versions: list[str] = [] # 코드 버전들
        self.latest_code: str = ""

    def _add_message(self, role: str, agent_name: str, text: str, is_code: bool = False):
        """대화 로그에 메시지를 추가한다."""
        self.log.append({
            "agent": agent_name,
            "role": role,
            "content": text,
            "is_code": is_code,
        })

    def _build_agent_messages(self, new_user_text: str) -> list[dict]:
        """Gemini API에 전달할 메시지를 구성한다."""
        msgs = []
        # 이전 대화 컨텍스트
        for m in self.messages:
            msgs.append(m)
        # 새 메시지
        msgs.append({"role": "user", "text": new_user_text})
        return msgs

    def run_chain(self, user_prompt: str, max_retries: int = 3) -> list[dict]:
        """1 라운드의 체인을 실행한다.

        Returns:
            로그 리스트
        """
        self.log = []

        # 1. Architect
        arch_msgs = self._build_agent_messages(user_prompt)
        arch_response = self.architect.run(arch_msgs, self.output_settings)
        self._add_message("model", "Architect", arch_response)
        self.messages.append({"role": "user", "text": user_prompt})
        self.messages.append({"role": "model", "text": f"[Architect] {arch_response}"})

        # 2. Coder
        coder_prompt = (
            f"Architect의 설계:\n{arch_response}\n\n"
            f"위 설계를 기반으로 Blender Python 코드를 작성해주세요."
        )
        if self.latest_code:
            coder_prompt += f"\n\n이전 코드:\n```python\n{self.latest_code}\n```"

        coder_msgs = self._build_agent_messages(coder_prompt)
        coder_response = self.coder.run(coder_msgs, self.output_settings)
        self._add_message("model", "Coder", coder_response, is_code=True)
        self.messages.append({"role": "model", "text": f"[Coder] {coder_response}"})

        # 3. Tester (코드 추출 → 실행 → 실패 시 Coder에게 리턴)
        code = TesterCls.extract_code(coder_response)
        if code:
            for attempt in range(max_retries):
                # AI Tester 분석
                tester_prompt = f"다음 Blender Python 코드를 검증해주세요:\n```python\n{code}\n```"
                tester_msgs = self._build_agent_messages(tester_prompt)
                tester_response = self.tester.run(tester_msgs, self.output_settings)
                self._add_message("model", "Tester", tester_response)

                # 실제 실행
                exec_result = TesterCls.execute_code(code)
                if exec_result["success"]:
                    self._add_message("model", "Tester", "[PASS] 코드 실행 성공")
                    self.messages.append({"role": "model", "text": "[Tester] PASS - 실행 성공"})
                    self.latest_code = code
                    self.code_versions.append(code)
                    break
                else:
                    error_msg = f"[FAIL] 실행 오류:\n{exec_result['error']}"
                    self._add_message("model", "Tester", error_msg)

                    if attempt < max_retries - 1:
                        # Coder에게 오류 수정 요청
                        fix_prompt = (
                            f"코드 실행 시 오류가 발생했습니다:\n{exec_result['error']}\n\n"
                            f"기존 코드:\n```python\n{code}\n```\n\n"
                            f"오류를 수정한 전체 코드를 작성해주세요."
                        )
                        fix_msgs = self._build_agent_messages(fix_prompt)
                        fix_response = self.coder.run(fix_msgs, self.output_settings)
                        self._add_message("model", "Coder", f"(수정 {attempt + 1}) {fix_response}", is_code=True)

                        new_code = TesterCls.extract_code(fix_response)
                        if new_code:
                            code = new_code
                        else:
                            self._add_message("model", "Tester", "[FAIL] 수정된 코드를 추출할 수 없습니다")
                            break
                    else:
                        self._add_message("model", "Tester", f"[FAIL] 최대 재시도 횟수({max_retries}) 초과")
                        self.messages.append({"role": "model", "text": f"[Tester] FAIL - 재시도 초과"})
        else:
            self._add_message("model", "Tester", "[FAIL] 코드 블록을 찾을 수 없습니다")

        # 4. Reviewer
        if self.latest_code:
            review_prompt = (
                f"다음 Blender 모델링 코드를 리뷰해주세요:\n"
                f"```python\n{self.latest_code}\n```\n\n"
                f"사용자 요청: {user_prompt}"
            )
            review_msgs = self._build_agent_messages(review_prompt)
            review_response = self.reviewer.run(review_msgs, self.output_settings)
            self._add_message("model", "Reviewer", review_response)
            self.messages.append({"role": "model", "text": f"[Reviewer] {review_response}"})

            # Reviewer가 수정 요청하면 Coder → Tester 한번 더
            if "[NEEDS_REVISION]" in review_response:
                revision_prompt = (
                    f"Reviewer 피드백:\n{review_response}\n\n"
                    f"기존 코드:\n```python\n{self.latest_code}\n```\n\n"
                    f"피드백을 반영하여 수정된 전체 코드를 작성해주세요."
                )
                rev_msgs = self._build_agent_messages(revision_prompt)
                rev_response = self.coder.run(rev_msgs, self.output_settings)
                self._add_message("model", "Coder", f"(리뷰 반영) {rev_response}", is_code=True)

                rev_code = TesterCls.extract_code(rev_response)
                if rev_code:
                    exec_result = TesterCls.execute_code(rev_code)
                    if exec_result["success"]:
                        self._add_message("model", "Tester", "[PASS] 수정 코드 실행 성공")
                        self.latest_code = rev_code
                        self.code_versions.append(rev_code)
                    else:
                        self._add_message("model", "Tester", f"[FAIL] {exec_result['error']}")

        # 5. Optimizer
        if self.latest_code:
            opt_prompt = (
                f"다음 코드를 최적화해주세요:\n"
                f"```python\n{self.latest_code}\n```"
            )
            opt_msgs = self._build_agent_messages(opt_prompt)
            opt_response = self.optimizer.run(opt_msgs, self.output_settings)
            self._add_message("model", "Optimizer", opt_response, is_code=True)

            opt_code = TesterCls.extract_code(opt_response)
            if opt_code:
                exec_result = TesterCls.execute_code(opt_code)
                if exec_result["success"]:
                    self._add_message("model", "Tester", "[PASS] 최적화 코드 실행 성공")
                    self.latest_code = opt_code
                    self.code_versions.append(opt_code)
                    self.messages.append({"role": "model", "text": f"[Optimizer] 최적화 완료"})
                else:
                    self._add_message("model", "Tester", f"[FAIL] 최적화 코드 오류 - 이전 버전 유지")

        return self.log

    def run_chat(self, user_feedback: str, max_retries: int = 3) -> list[dict]:
        """대화형 수정 요청을 처리한다."""
        self.log = []

        chat_prompt = (
            f"사용자 수정 요청: {user_feedback}\n\n"
            f"현재 코드:\n```python\n{self.latest_code}\n```\n\n"
            f"수정 요청을 반영한 전체 코드를 작성해주세요."
        )

        # Coder → Tester 체인
        coder_msgs = self._build_agent_messages(chat_prompt)
        coder_response = self.coder.run(coder_msgs, self.output_settings)
        self._add_message("model", "Coder", coder_response, is_code=True)
        self.messages.append({"role": "user", "text": user_feedback})
        self.messages.append({"role": "model", "text": f"[Coder] {coder_response}"})

        code = TesterCls.extract_code(coder_response)
        if code:
            for attempt in range(max_retries):
                exec_result = TesterCls.execute_code(code)
                if exec_result["success"]:
                    self._add_message("model", "Tester", "[PASS] 실행 성공")
                    self.latest_code = code
                    self.code_versions.append(code)
                    break
                else:
                    error_msg = f"[FAIL] {exec_result['error']}"
                    self._add_message("model", "Tester", error_msg)
                    if attempt < max_retries - 1:
                        fix_prompt = (
                            f"오류 발생:\n{exec_result['error']}\n\n"
                            f"코드:\n```python\n{code}\n```\n\n수정해주세요."
                        )
                        fix_msgs = self._build_agent_messages(fix_prompt)
                        fix_response = self.coder.run(fix_msgs, self.output_settings)
                        self._add_message("model", "Coder", f"(수정) {fix_response}", is_code=True)
                        new_code = TesterCls.extract_code(fix_response)
                        if new_code:
                            code = new_code
                        else:
                            break
        else:
            self._add_message("model", "Tester", "[FAIL] 코드 블록을 찾을 수 없습니다")

        return self.log
