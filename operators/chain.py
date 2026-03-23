"""에이전트 체인 실행 오퍼레이터"""

import threading
import bpy

# 체인 러너 인스턴스를 모듈 레벨에서 관리
_chain_runner = None


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


def _get_api_key() -> str:
    prefs = bpy.context.preferences.addons.get(__package__.split(".")[0])
    if prefs:
        return prefs.preferences.api_key
    return ""


class NUP_OT_RunChain(bpy.types.Operator):
    bl_idname = "nup.run_chain"
    bl_label = "체인 실행"
    bl_description = "에이전트 체인을 실행하여 모델링 코드를 생성합니다"

    _timer = None
    _thread = None
    _result = None
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

        if _chain_runner is None:
            _chain_runner = ChainRunner(api_key, _get_output_settings(scene))
        else:
            _chain_runner.output_settings = _get_output_settings(scene)

        scene.nup_is_running = True
        scene.nup_current_round += 1

        # 백그라운드 스레드에서 체인 실행 (UI 멈춤 방지)
        NUP_OT_RunChain._running = True
        NUP_OT_RunChain._result = None
        NUP_OT_RunChain._thread = threading.Thread(
            target=self._run_in_thread,
            args=(prompt, scene.nup_max_retries),
        )
        NUP_OT_RunChain._thread.start()

        # 타이머로 완료 체크
        NUP_OT_RunChain._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _run_in_thread(self, prompt, max_retries):
        global _chain_runner
        try:
            result = _chain_runner.run_chain(prompt, max_retries)
            NUP_OT_RunChain._result = result
        except Exception as e:
            NUP_OT_RunChain._result = [{"agent": "System", "role": "model", "content": f"오류: {e}", "is_code": False}]
        NUP_OT_RunChain._running = False

    def modal(self, context, event):
        if event.type == "TIMER":
            if not NUP_OT_RunChain._running:
                # 완료
                context.window_manager.event_timer_remove(NUP_OT_RunChain._timer)
                NUP_OT_RunChain._timer = None

                scene = context.scene
                scene.nup_is_running = False

                # 결과를 scene 메시지에 추가
                if NUP_OT_RunChain._result:
                    for msg in NUP_OT_RunChain._result:
                        item = scene.nup_messages.add()
                        item.role = msg["agent"]
                        item.content = msg["content"]
                        item.is_code = msg.get("is_code", False)

                # 코드 버전 업데이트
                global _chain_runner
                if _chain_runner and _chain_runner.code_versions:
                    scene.nup_code_versions.clear()
                    for i, code in enumerate(_chain_runner.code_versions):
                        cv = scene.nup_code_versions.add()
                        cv.version = i + 1
                        cv.code = code
                        cv.status = "success"
                    scene.nup_active_code_version = len(_chain_runner.code_versions)

                # UI 갱신
                for area in context.screen.areas:
                    area.tag_redraw()

                self.report({"INFO"}, "체인 실행 완료")
                return {"FINISHED"}

        return {"PASS_THROUGH"}

    def cancel(self, context):
        if NUP_OT_RunChain._timer:
            context.window_manager.event_timer_remove(NUP_OT_RunChain._timer)
            NUP_OT_RunChain._timer = None


class NUP_OT_StopChain(bpy.types.Operator):
    bl_idname = "nup.stop_chain"
    bl_label = "중단"
    bl_description = "체인 실행을 중단합니다"

    def execute(self, context):
        NUP_OT_RunChain._running = False
        context.scene.nup_is_running = False
        self.report({"INFO"}, "체인 중단됨")
        return {"FINISHED"}
