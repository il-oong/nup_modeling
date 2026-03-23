"""에이전트 체인 실행 오퍼레이터"""

import threading
import bpy

# 체인 러너 인스턴스를 모듈 레벨에서 관리
_chain_runner = None
_lock = threading.Lock()


def get_chain_runner():
    global _chain_runner
    return _chain_runner


def _get_output_settings(scene) -> dict:
    return {
        "style": scene.nup_output_style,
        "purpose": scene.nup_output_purpose,
        "format": scene.nup_output_format,
        "max_polys": scene.nup_output_max_polys,
        "material": scene.nup_output_material,
    }


def _get_prefs():
    prefs = bpy.context.preferences.addons.get(__package__.split(".")[0])
    if prefs:
        return prefs.preferences
    return None


def _get_api_key() -> str:
    prefs = _get_prefs()
    return prefs.api_key if prefs else ""


def _get_model() -> str:
    prefs = _get_prefs()
    return prefs.model_name if prefs and prefs.model_name else "gemini-3-flash-preview"


def _sync_log_to_scene(scene, log):
    """체인 러너의 로그를 scene 메시지에 동기화한다."""
    current_count = len(scene.nup_messages)
    for i in range(current_count, len(log)):
        msg = log[i]
        item = scene.nup_messages.add()
        item.role = msg["agent"]
        item.content = msg["content"]
        item.is_code = msg.get("is_code", False)


def _sync_code_versions(scene, runner):
    """코드 버전을 scene에 동기화한다."""
    if runner and runner.code_versions:
        scene.nup_code_versions.clear()
        for i, code in enumerate(runner.code_versions):
            cv = scene.nup_code_versions.add()
            cv.version = i + 1
            cv.code = code
            cv.status = "success"
        scene.nup_active_code_version = len(runner.code_versions)


def _redraw_all(context):
    """모든 영역을 다시 그린다."""
    for area in context.screen.areas:
        area.tag_redraw()


class NUP_OT_RunChain(bpy.types.Operator):
    bl_idname = "nup.run_chain"
    bl_label = "체인 실행"
    bl_description = "에이전트 체인을 실행하여 모델링 코드를 생성합니다"

    _timer = None
    _thread = None
    _api_done = False
    _running = False

    def execute(self, context):
        scene = context.scene
        prompt = scene.nup_prompt.strip()

        if not prompt:
            self.report({"WARNING"}, "모델링 요청을 입력하세요")
            return {"CANCELLED"}

        api_key = _get_api_key()
        if not api_key:
            self.report({"WARNING"}, "설정에서 API 키를 입력하세요 (Edit > Preferences > Add-ons > NUP Modeling)")
            return {"CANCELLED"}

        global _chain_runner
        from ..core.chain_runner import ChainRunner

        model = _get_model()
        if _chain_runner is None:
            _chain_runner = ChainRunner(api_key, _get_output_settings(scene), model)
        else:
            _chain_runner.output_settings = _get_output_settings(scene)

        scene.nup_is_running = True
        scene.nup_current_round += 1

        # 백그라운드 스레드에서 API 호출만 수행
        NUP_OT_RunChain._api_done = False
        NUP_OT_RunChain._running = True
        NUP_OT_RunChain._thread = threading.Thread(
            target=self._run_api_thread,
            args=(prompt, scene.nup_max_retries),
            daemon=True,
        )
        NUP_OT_RunChain._thread.start()

        # 0.3초마다 로그 업데이트 체크 (실시간 스트리밍 효과)
        NUP_OT_RunChain._timer = context.window_manager.event_timer_add(0.3, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _run_api_thread(self, prompt, max_retries):
        global _chain_runner
        try:
            _chain_runner.run_chain_api_only(prompt, max_retries)
        except Exception as e:
            _chain_runner._add_message("model", "System", f"오류: {e}")
        NUP_OT_RunChain._api_done = True

    def modal(self, context, event):
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        scene = context.scene
        global _chain_runner

        if not NUP_OT_RunChain._running:
            self._cleanup(context)
            scene.nup_is_running = False
            return {"FINISHED"}

        # 실시간 로그 동기화 (스트리밍 효과)
        if _chain_runner:
            _sync_log_to_scene(scene, _chain_runner.log)
            _redraw_all(context)

        # API 호출 완료 → 메인 스레드에서 코드 실행
        if NUP_OT_RunChain._api_done:
            NUP_OT_RunChain._api_done = False

            if _chain_runner and _chain_runner.pending_exec:
                # 메인 스레드에서 exec() 실행
                result = _chain_runner.execute_pending()
                _sync_log_to_scene(scene, _chain_runner.log)
                _sync_code_versions(scene, _chain_runner)

                if not result["success"]:
                    self.report({"WARNING"}, f"코드 실행 실패: {result['error'][:100]}")
                else:
                    self.report({"INFO"}, "체인 완료 - 코드 실행 성공")
            else:
                _sync_log_to_scene(scene, _chain_runner.log if _chain_runner else [])
                self.report({"WARNING"}, "체인 완료 - 실행할 코드 없음")

            _redraw_all(context)
            NUP_OT_RunChain._running = False
            self._cleanup(context)
            scene.nup_is_running = False
            return {"FINISHED"}

        return {"PASS_THROUGH"}

    def _cleanup(self, context):
        if NUP_OT_RunChain._timer:
            context.window_manager.event_timer_remove(NUP_OT_RunChain._timer)
            NUP_OT_RunChain._timer = None

    def cancel(self, context):
        self._cleanup(context)


class NUP_OT_StopChain(bpy.types.Operator):
    bl_idname = "nup.stop_chain"
    bl_label = "중단"
    bl_description = "체인 실행을 중단합니다"

    def execute(self, context):
        NUP_OT_RunChain._running = False
        NUP_OT_RunChain._api_done = False
        context.scene.nup_is_running = False
        self.report({"INFO"}, "체인 중단됨")
        return {"FINISHED"}
