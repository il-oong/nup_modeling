"""에이전트 체인 루프 관리 - 컨텍스트 최적화 버전"""

import threading
from typing import Optional

from ..agents import (
    PrompterAgent,
    ArchitectAgent,
    CoderAgent,
    TesterAgent,
    ReviewerAgent,
    OptimizerAgent,
    VFXAgent,
)


# 최대 메시지 히스토리 수 (토큰 절약)
_MAX_HISTORY = 6


def _trim_messages(messages: list[dict], max_count: int = _MAX_HISTORY) -> list[dict]:
    """메시지 히스토리를 최근 N개로 제한하여 토큰을 절약한다."""
    if len(messages) <= max_count:
        return messages
    return messages[-max_count:]


def _summarize_response(text: str, max_len: int = 500) -> str:
    """긴 응답을 요약하여 컨텍스트에 저장한다."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n...(생략)"


class ChainRunner:
    """에이전트 체인을 순서대로 실행한다.

    API 호출은 백그라운드 스레드에서,
    코드 실행(exec)은 메인 스레드에서 수행하도록 분리한다.
    """

    def __init__(self, api_key: str, output_settings: dict, model: str = "gemini-3-flash-preview"):
        self.api_key = api_key
        self.output_settings = output_settings
        self.model = model
        self._init_agents(api_key, model)

        self.messages: list[dict] = []
        self.log: list[dict] = []
        self.code_versions: list[str] = []
        self.latest_code: str = ""

        self.pending_exec: Optional[str] = None
        self.exec_result: Optional[dict] = None

        # 스레드 안전을 위한 Lock
        self._log_lock = threading.Lock()

    def _init_agents(self, api_key: str, model: str):
        """에이전트들을 (재)초기화한다."""
        self.prompter = PrompterAgent(api_key, model)
        self.architect = ArchitectAgent(api_key, model)
        self.coder = CoderAgent(api_key, model)
        self.tester = TesterAgent(api_key, model)
        self.reviewer = ReviewerAgent(api_key, model)
        self.optimizer = OptimizerAgent(api_key, model)
        self.vfx = VFXAgent(api_key, model)

    def update_settings(self, api_key: str, model: str, output_settings: dict):
        """API 키, 모델, 아웃풋 설정을 갱신한다."""
        if api_key != self.api_key or model != self.model:
            self.api_key = api_key
            self.model = model
            self._init_agents(api_key, model)
        self.output_settings = output_settings

    def _add_message(self, role: str, agent_name: str, text: str, is_code: bool = False):
        with self._log_lock:
            self.log.append({
                "agent": agent_name,
                "role": role,
                "content": text,
                "is_code": is_code,
            })

    def get_log_snapshot(self) -> list[dict]:
        """스레드 안전한 로그 스냅샷을 반환한다."""
        with self._log_lock:
            return list(self.log)

    def _build_agent_messages(self, new_user_text: str) -> list[dict]:
        """Gemini API에 전달할 메시지를 구성한다.
        히스토리를 제한하고 연속 동일 role을 병합하여 토큰을 절약한다.
        """
        # 히스토리 제한 (토큰 절약 핵심)
        trimmed = _trim_messages(self.messages)
        msgs = list(trimmed)
        msgs.append({"role": "user", "text": new_user_text})

        # 연속 동일 role 병합
        merged = []
        for msg in msgs:
            if merged and merged[-1]["role"] == msg["role"]:
                merged[-1]["text"] += "\n\n" + msg["text"]
            else:
                merged.append(dict(msg))
        return merged

    def _build_fresh_messages(self, text: str) -> list[dict]:
        """히스토리 없이 새 메시지만 구성한다 (토큰 최소화)."""
        return [{"role": "user", "text": text}]

    def run_chain_api_only(self, user_prompt: str, max_retries: int = 3,
                           image_path: str = "", image_description: str = "") -> list[dict]:
        """체인에서 API 호출만 수행한다 (스레드 안전)."""
        self.log = []
        code = None

        # 참고 이미지 + 설명
        full_prompt = user_prompt
        if image_path:
            self._add_message("model", "System", f"참고 이미지: {image_path}")
        if image_description:
            full_prompt += f"\n\n[참고 이미지 설명]\n{image_description}"

        # 0. Prompter - 프롬프트 구체화 (히스토리 없이 단독 호출 → 토큰 절약)
        self._add_message("model", "Prompter", "프롬프트를 분석하고 구체화합니다...")
        prompter_msgs = self._build_fresh_messages(full_prompt)
        prompter_response = self.prompter.run(prompter_msgs, self.output_settings, image_path=image_path)
        self._add_message("model", "Prompter", prompter_response)
        enhanced_prompt = f"{user_prompt}\n\n[프롬프터 분석]\n{prompter_response}"

        # 1. Architect (히스토리 없이 → 토큰 절약)
        self._add_message("model", "Architect", "모델링 구조를 설계합니다...")
        arch_msgs = self._build_fresh_messages(enhanced_prompt)
        arch_response = self.architect.run(arch_msgs, self.output_settings, image_path=image_path)
        self._add_message("model", "Architect", arch_response)

        # 컨텍스트에는 요약만 저장 (토큰 절약)
        self.messages.append({"role": "user", "text": user_prompt})
        self.messages.append({"role": "model", "text": f"[설계 요약] {_summarize_response(arch_response, 300)}"})

        # 2. Coder (설계 결과만 전달 → 토큰 절약)
        coder_prompt = (
            f"설계:\n{arch_response}\n\n"
            f"위 설계를 기반으로 Blender Python 코드를 작성해주세요."
        )
        if self.latest_code:
            coder_prompt += f"\n\n이전 코드:\n```python\n{self.latest_code}\n```"
        if image_description:
            coder_prompt += f"\n\n[참고 이미지 설명]\n{image_description}"

        self._add_message("model", "Coder", "코드를 작성합니다...")
        coder_msgs = self._build_fresh_messages(coder_prompt)
        coder_response = self.coder.run(coder_msgs, self.output_settings, image_path=image_path)
        self._add_message("model", "Coder", coder_response, is_code=True)

        # 3. Tester (AI 분석만)
        code = TesterAgent.extract_code(coder_response)
        if code:
            safety_error = TesterAgent.check_code_safety(code)
            if safety_error:
                self._add_message("model", "Tester", f"[FAIL] 안전성 검사 실패: {safety_error}")
                for attempt in range(max_retries):
                    fix_prompt = (
                        f"안전성 실패:\n{safety_error}\n\n"
                        f"코드:\n```python\n{code}\n```\n\n"
                        f"안전한 코드로 수정. os, subprocess 금지."
                    )
                    fix_msgs = self._build_fresh_messages(fix_prompt)
                    fix_response = self.coder.run(fix_msgs, self.output_settings)
                    self._add_message("model", "Coder", f"(수정 {attempt + 1}) {fix_response}", is_code=True)

                    new_code = TesterAgent.extract_code(fix_response)
                    if new_code:
                        safety_error = TesterAgent.check_code_safety(new_code)
                        if not safety_error:
                            code = new_code
                            break
                        code = new_code
                    else:
                        break

            # AI Tester 분석 (코드만 전달 → 토큰 절약)
            self._add_message("model", "Tester", "코드를 검증합니다...")
            tester_prompt = f"다음 Blender Python 코드를 검증:\n```python\n{code}\n```"
            tester_msgs = self._build_fresh_messages(tester_prompt)
            tester_response = self.tester.run(tester_msgs, self.output_settings)
            self._add_message("model", "Tester", tester_response)

            tester_passed = "[PASS]" in tester_response

            if not tester_passed:
                for attempt in range(max_retries):
                    fix_prompt = (
                        f"Tester 오류:\n{tester_response}\n\n"
                        f"코드:\n```python\n{code}\n```\n\n"
                        f"오류를 수정한 전체 코드를 작성."
                    )
                    fix_msgs = self._build_fresh_messages(fix_prompt)
                    fix_response = self.coder.run(fix_msgs, self.output_settings)
                    self._add_message("model", "Coder", f"(수정 {attempt + 1}) {fix_response}", is_code=True)

                    new_code = TesterAgent.extract_code(fix_response)
                    if new_code:
                        code = new_code
                        re_test_msgs = self._build_fresh_messages(
                            f"수정된 코드 검증:\n```python\n{code}\n```"
                        )
                        re_test_response = self.tester.run(re_test_msgs, self.output_settings)
                        self._add_message("model", "Tester", re_test_response)
                        if "[PASS]" in re_test_response:
                            tester_passed = True
                            break
                        tester_response = re_test_response
                    else:
                        break

            if tester_passed:
                self.pending_exec = code
            else:
                self._add_message("model", "Tester", "[BLOCKED] Tester 미통과 - 코드 실행 차단")
                self.pending_exec = None

            # 컨텍스트에 코드 요약만 저장
            self.messages.append({"role": "user", "text": "코드 생성 완료"})
            self.messages.append({"role": "model", "text": "[Tester] 코드 분석 완료"})
        else:
            self._add_message("model", "Tester", "[FAIL] 코드 블록을 찾을 수 없습니다")
            self.pending_exec = None

        # 4. Reviewer (코드 + 설정만 전달 → 토큰 절약)
        if code:
            review_prompt = (
                f"코드 리뷰:\n```python\n{code}\n```\n\n"
                f"요청: {user_prompt}\n"
                f"최대 폴리곤: {self.output_settings.get('max_polys', 1000)}"
            )
            self._add_message("model", "Reviewer", "코드를 리뷰합니다...")
            review_msgs = self._build_fresh_messages(review_prompt)
            review_response = self.reviewer.run(review_msgs, self.output_settings)
            self._add_message("model", "Reviewer", review_response)

            if "[NEEDS_REVISION]" in review_response:
                revision_prompt = (
                    f"리뷰 피드백:\n{review_response}\n\n"
                    f"코드:\n```python\n{code}\n```\n\n"
                    f"피드백을 반영하여 수정된 전체 코드를 작성."
                )
                rev_msgs = self._build_fresh_messages(revision_prompt)
                rev_response = self.coder.run(rev_msgs, self.output_settings)
                self._add_message("model", "Coder", f"(리뷰 반영) {rev_response}", is_code=True)

                rev_code = TesterAgent.extract_code(rev_response)
                if rev_code:
                    safety_err = TesterAgent.check_code_safety(rev_code)
                    if not safety_err:
                        code = rev_code
                        self.pending_exec = code
                    else:
                        self._add_message("model", "Tester", f"리뷰 수정 안전성 실패: {safety_err}")

        # 5. Optimizer (코드만 전달 → 토큰 절약)
        if code:
            opt_prompt = f"최적화:\n```python\n{code}\n```\n최대 폴리곤: {self.output_settings.get('max_polys', 1000)}"
            self._add_message("model", "Optimizer", "코드를 최적화합니다...")
            opt_msgs = self._build_fresh_messages(opt_prompt)
            opt_response = self.optimizer.run(opt_msgs, self.output_settings)
            self._add_message("model", "Optimizer", opt_response, is_code=True)

            opt_code = TesterAgent.extract_code(opt_response)
            if opt_code:
                safety_err = TesterAgent.check_code_safety(opt_code)
                if not safety_err:
                    code = opt_code
                    self.pending_exec = code
                else:
                    self._add_message("model", "Tester", "최적화 코드 안전성 실패 - 이전 버전 유지")

            # 컨텍스트 요약 저장
            self.messages.append({"role": "user", "text": "코드 최적화 완료"})
            self.messages.append({"role": "model", "text": "[Optimizer] 최적화 완료"})

        # 6. VFX (활성화된 경우)
        vfx_list = self.output_settings.get("vfx", [])
        safe_code_backup = code
        if code and vfx_list:
            vfx_prompt = (
                f"VFX 추가:\n```python\n{code}\n```\n\n"
                f"VFX: {', '.join(vfx_list)}\n"
                f"기존 코드에 VFX를 통합. try/except로 개별 실패 방지."
            )
            self._add_message("model", "VFX", "VFX 이펙트를 추가합니다...")
            vfx_msgs = self._build_fresh_messages(vfx_prompt)
            vfx_response = self.vfx.run(vfx_msgs, self.output_settings)
            self._add_message("model", "VFX", vfx_response, is_code=True)

            vfx_code = TesterAgent.extract_code(vfx_response)
            if vfx_code:
                safety_err = TesterAgent.check_code_safety(vfx_code)
                if not safety_err:
                    vfx_test_msgs = self._build_fresh_messages(
                        f"VFX 코드 검증:\n```python\n{vfx_code}\n```"
                    )
                    vfx_test_response = self.tester.run(vfx_test_msgs, self.output_settings)
                    self._add_message("model", "Tester", vfx_test_response)

                    if "[PASS]" in vfx_test_response:
                        code = vfx_code
                        self.pending_exec = code
                        self._add_message("model", "VFX", "VFX 코드 적용됨")
                    else:
                        self._add_message("model", "VFX", "[WARNING] VFX 검증 실패 - VFX 없이 진행")
                        code = safe_code_backup
                        self.pending_exec = code
                else:
                    self._add_message("model", "Tester", f"VFX 안전성 실패: {safety_err}")

        return self.get_log_snapshot()

    def execute_pending(self, live_preview: bool = False) -> dict:
        """대기 중인 코드를 메인 스레드에서 실행한다."""
        if not self.pending_exec:
            return {"success": False, "error": "실행할 코드가 없습니다"}

        if live_preview:
            result = TesterAgent.execute_code_stepwise(self.pending_exec, step_delay=0.3)
        else:
            result = TesterAgent.execute_code(self.pending_exec)

        if result.get("success"):
            self.latest_code = self.pending_exec
            self.code_versions.append(self.pending_exec)
            self._add_message("model", "Tester", "[PASS] 코드 실행 성공")
        elif not result.get("stepwise"):
            self._add_message("model", "Tester", f"[FAIL] 실행 오류: {result['error']}")

        self.exec_result = result
        self.pending_exec = None
        return result

    def run_chat_api_only(self, user_feedback: str, max_retries: int = 3) -> list[dict]:
        """대화형 수정 - API 호출만 (스레드 안전). 토큰 최적화 적용."""
        self.log = []
        code = None

        # 코드 + 피드백만 전달 (히스토리 불필요 → 토큰 절약)
        chat_prompt = (
            f"수정 요청: {user_feedback}\n\n"
            f"현재 코드:\n```python\n{self.latest_code}\n```\n\n"
            f"수정된 전체 코드를 작성."
        )

        self._add_message("model", "Coder", f"수정 요청을 처리합니다: {user_feedback[:50]}...")
        coder_msgs = self._build_fresh_messages(chat_prompt)
        coder_response = self.coder.run(coder_msgs, self.output_settings)
        self._add_message("model", "Coder", coder_response, is_code=True)
        self.messages.append({"role": "user", "text": user_feedback})
        self.messages.append({"role": "model", "text": f"[Coder] 수정 완료"})

        code = TesterAgent.extract_code(coder_response)
        if code:
            safety_err = TesterAgent.check_code_safety(code)
            if safety_err:
                self._add_message("model", "Tester", f"[FAIL] 안전성: {safety_err}")
            else:
                self.pending_exec = code

                self._add_message("model", "Tester", "수정된 코드를 검증합니다...")
                tester_msgs = self._build_fresh_messages(
                    f"코드 검증:\n```python\n{code}\n```"
                )
                tester_response = self.tester.run(tester_msgs, self.output_settings)
                self._add_message("model", "Tester", tester_response)

                tester_passed = "[PASS]" in tester_response

                if not tester_passed:
                    for attempt in range(max_retries):
                        fix_prompt = (
                            f"Tester 오류:\n{tester_response}\n\n"
                            f"코드:\n```python\n{code}\n```\n\n"
                            f"오류 수정한 전체 코드를 작성."
                        )
                        fix_msgs = self._build_fresh_messages(fix_prompt)
                        fix_response = self.coder.run(fix_msgs, self.output_settings)
                        self._add_message("model", "Coder", f"(수정 {attempt + 1}) {fix_response}", is_code=True)
                        new_code = TesterAgent.extract_code(fix_response)
                        if new_code:
                            code = new_code
                            re_test_msgs = self._build_fresh_messages(
                                f"수정 코드 검증:\n```python\n{code}\n```"
                            )
                            re_test_response = self.tester.run(re_test_msgs, self.output_settings)
                            self._add_message("model", "Tester", re_test_response)
                            if "[PASS]" in re_test_response:
                                tester_passed = True
                                self.pending_exec = code
                                break
                            tester_response = re_test_response
                        else:
                            break

                    if not tester_passed:
                        self._add_message("model", "Tester", "[BLOCKED] Tester 미통과 - 코드 실행 차단")
                        self.pending_exec = None
        else:
            self._add_message("model", "Tester", "[FAIL] 코드 블록을 찾을 수 없습니다")

        return self.get_log_snapshot()
