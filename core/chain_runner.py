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
    """에이전트 체인을 순서대로 실행한다.

    API 호출은 백그라운드 스레드에서,
    코드 실행(exec)은 메인 스레드에서 수행하도록 분리한다.
    """

    def __init__(self, api_key: str, output_settings: dict, model: str = "gemini-3-flash-preview"):
        self.api_key = api_key
        self.output_settings = output_settings
        self.model = model
        self.architect = ArchitectAgent(api_key, model)
        self.coder = CoderAgent(api_key, model)
        self.tester = TesterAgent(api_key, model)
        self.reviewer = ReviewerAgent(api_key, model)
        self.optimizer = OptimizerAgent(api_key, model)

        self.messages: list[dict] = []     # 전체 대화 히스토리
        self.log: list[dict] = []          # UI 표시용 로그
        self.code_versions: list[str] = [] # 코드 버전들
        self.latest_code: str = ""

        # 메인 스레드에서 실행할 코드 큐
        self.pending_exec: str | None = None
        self.exec_result: dict | None = None

    def _add_message(self, role: str, agent_name: str, text: str, is_code: bool = False):
        self.log.append({
            "agent": agent_name,
            "role": role,
            "content": text,
            "is_code": is_code,
        })

    def _build_agent_messages(self, new_user_text: str) -> list[dict]:
        msgs = list(self.messages)
        msgs.append({"role": "user", "text": new_user_text})
        return msgs

    def run_chain_api_only(self, user_prompt: str, max_retries: int = 3) -> list[dict]:
        """체인에서 API 호출만 수행한다 (스레드 안전).

        exec()은 수행하지 않고, AI Tester의 코드 분석만 진행한다.
        실제 코드 실행은 메인 스레드에서 별도로 수행해야 한다.
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

        # 3. Tester (AI 분석만 - exec 없음)
        code = TesterCls.extract_code(coder_response)
        if code:
            # AST 안전성 검사 (스레드 안전)
            safety_error = TesterCls.check_code_safety(code)
            if safety_error:
                self._add_message("model", "Tester", f"[FAIL] 안전성 검사 실패: {safety_error}")
                # Coder에게 수정 요청
                for attempt in range(max_retries):
                    fix_prompt = (
                        f"코드 안전성 검사 실패:\n{safety_error}\n\n"
                        f"기존 코드:\n```python\n{code}\n```\n\n"
                        f"안전한 코드로 수정해주세요. os, subprocess 등 시스템 모듈을 사용하지 마세요."
                    )
                    fix_msgs = self._build_agent_messages(fix_prompt)
                    fix_response = self.coder.run(fix_msgs, self.output_settings)
                    self._add_message("model", "Coder", f"(수정 {attempt + 1}) {fix_response}", is_code=True)

                    new_code = TesterCls.extract_code(fix_response)
                    if new_code:
                        safety_error = TesterCls.check_code_safety(new_code)
                        if not safety_error:
                            code = new_code
                            break
                        code = new_code
                    else:
                        break

            # AI Tester 분석
            tester_prompt = f"다음 Blender Python 코드를 검증해주세요:\n```python\n{code}\n```"
            tester_msgs = self._build_agent_messages(tester_prompt)
            tester_response = self.tester.run(tester_msgs, self.output_settings)
            self._add_message("model", "Tester", tester_response)

            if "[FAIL]" in tester_response:
                # AI가 문제를 발견하면 Coder에게 수정 요청
                for attempt in range(max_retries):
                    fix_prompt = (
                        f"Tester 피드백:\n{tester_response}\n\n"
                        f"기존 코드:\n```python\n{code}\n```\n\n"
                        f"오류를 수정한 전체 코드를 작성해주세요."
                    )
                    fix_msgs = self._build_agent_messages(fix_prompt)
                    fix_response = self.coder.run(fix_msgs, self.output_settings)
                    self._add_message("model", "Coder", f"(수정 {attempt + 1}) {fix_response}", is_code=True)

                    new_code = TesterCls.extract_code(fix_response)
                    if new_code:
                        code = new_code
                        # 재검증
                        re_test_msgs = self._build_agent_messages(
                            f"수정된 코드를 다시 검증해주세요:\n```python\n{code}\n```"
                        )
                        re_test_response = self.tester.run(re_test_msgs, self.output_settings)
                        self._add_message("model", "Tester", re_test_response)
                        if "[PASS]" in re_test_response:
                            break
                        tester_response = re_test_response
                    else:
                        break

            # 메인 스레드에서 실행할 코드 저장
            self.pending_exec = code
            self.messages.append({"role": "model", "text": f"[Tester] 코드 분석 완료"})
        else:
            self._add_message("model", "Tester", "[FAIL] 코드 블록을 찾을 수 없습니다")
            self.pending_exec = None

        # 4. Reviewer
        if code:
            review_prompt = (
                f"다음 Blender 모델링 코드를 리뷰해주세요:\n"
                f"```python\n{code}\n```\n\n"
                f"사용자 요청: {user_prompt}"
            )
            review_msgs = self._build_agent_messages(review_prompt)
            review_response = self.reviewer.run(review_msgs, self.output_settings)
            self._add_message("model", "Reviewer", review_response)
            self.messages.append({"role": "model", "text": f"[Reviewer] {review_response}"})

            # Reviewer 수정 요청 시
            if "[NEEDS_REVISION]" in review_response:
                revision_prompt = (
                    f"Reviewer 피드백:\n{review_response}\n\n"
                    f"기존 코드:\n```python\n{code}\n```\n\n"
                    f"피드백을 반영하여 수정된 전체 코드를 작성해주세요."
                )
                rev_msgs = self._build_agent_messages(revision_prompt)
                rev_response = self.coder.run(rev_msgs, self.output_settings)
                self._add_message("model", "Coder", f"(리뷰 반영) {rev_response}", is_code=True)

                rev_code = TesterCls.extract_code(rev_response)
                if rev_code:
                    code = rev_code
                    self.pending_exec = code

        # 5. Optimizer
        if code:
            opt_prompt = f"다음 코드를 최적화해주세요:\n```python\n{code}\n```"
            opt_msgs = self._build_agent_messages(opt_prompt)
            opt_response = self.optimizer.run(opt_msgs, self.output_settings)
            self._add_message("model", "Optimizer", opt_response, is_code=True)

            opt_code = TesterCls.extract_code(opt_response)
            if opt_code:
                safety_err = TesterCls.check_code_safety(opt_code)
                if not safety_err:
                    code = opt_code
                    self.pending_exec = code
                else:
                    self._add_message("model", "Tester", f"최적화 코드 안전성 실패 - 이전 버전 유지")

            self.messages.append({"role": "model", "text": "[Optimizer] 최적화 완료"})

        return self.log

    def execute_pending(self) -> dict:
        """대기 중인 코드를 메인 스레드에서 실행한다.

        반드시 Blender 메인 스레드에서 호출해야 한다.
        """
        if not self.pending_exec:
            return {"success": False, "error": "실행할 코드가 없습니다"}

        result = TesterCls.execute_code(self.pending_exec)
        if result["success"]:
            self.latest_code = self.pending_exec
            self.code_versions.append(self.pending_exec)
            self._add_message("model", "Tester", "[PASS] 코드 실행 성공 ✓")
        else:
            self._add_message("model", "Tester", f"[FAIL] 실행 오류: {result['error']}")

        self.exec_result = result
        self.pending_exec = None
        return result

    def run_chat_api_only(self, user_feedback: str, max_retries: int = 3) -> list[dict]:
        """대화형 수정 - API 호출만 (스레드 안전)."""
        self.log = []

        chat_prompt = (
            f"사용자 수정 요청: {user_feedback}\n\n"
            f"현재 코드:\n```python\n{self.latest_code}\n```\n\n"
            f"수정 요청을 반영한 전체 코드를 작성해주세요."
        )

        coder_msgs = self._build_agent_messages(chat_prompt)
        coder_response = self.coder.run(coder_msgs, self.output_settings)
        self._add_message("model", "Coder", coder_response, is_code=True)
        self.messages.append({"role": "user", "text": user_feedback})
        self.messages.append({"role": "model", "text": f"[Coder] {coder_response}"})

        code = TesterCls.extract_code(coder_response)
        if code:
            safety_err = TesterCls.check_code_safety(code)
            if safety_err:
                self._add_message("model", "Tester", f"[FAIL] 안전성: {safety_err}")
            else:
                self.pending_exec = code

                # AI 검증
                tester_prompt = f"다음 코드를 검증해주세요:\n```python\n{code}\n```"
                tester_msgs = self._build_agent_messages(tester_prompt)
                tester_response = self.tester.run(tester_msgs, self.output_settings)
                self._add_message("model", "Tester", tester_response)

                if "[FAIL]" in tester_response:
                    for attempt in range(max_retries):
                        fix_prompt = (
                            f"오류:\n{tester_response}\n\n"
                            f"코드:\n```python\n{code}\n```\n\n수정해주세요."
                        )
                        fix_msgs = self._build_agent_messages(fix_prompt)
                        fix_response = self.coder.run(fix_msgs, self.output_settings)
                        self._add_message("model", "Coder", f"(수정) {fix_response}", is_code=True)
                        new_code = TesterCls.extract_code(fix_response)
                        if new_code:
                            code = new_code
                            self.pending_exec = code
                        else:
                            break
        else:
            self._add_message("model", "Tester", "[FAIL] 코드 블록을 찾을 수 없습니다")

        return self.log
