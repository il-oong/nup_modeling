"""대화형 수정 오퍼레이터"""

import threading
import bpy

from .chain import get_chain_runner, _sync_log_to_scene, _sync_code_versions, _redraw_all


class NUP_OT_SendChat(bpy.types.Operator):
    bl_idname = "nup.send_chat"
    bl_label = "전송"
    bl_description = "대화형 수정 요청을 전송합니다"

    _timer = None
    _thread = None
    _api_done = False
    _running = False
    _runner_ref = None  # 스레드에 직접 전달

    def execute(self, context):
        scene = context.scene
        chat_input = scene.nup_chat_input.strip()

        if not chat_input:
            self.report({"WARNING"}, "수정 요청을 입력하세요")
            return {"CANCELLED"}

        runner = get_chain_runner()
        if runner is None or not runner.latest_code:
            self.report({"WARNING"}, "먼저 체인을 실행하세요")
            return {"CANCELLED"}

        # 사용자 메시지 추가
        item = scene.nup_messages.add()
        item.role = "User"
        item.content = chat_input
        item.is_code = False

        scene.nup_is_running = True

        NUP_OT_SendChat._runner_ref = runner
        NUP_OT_SendChat._api_done = False
        NUP_OT_SendChat._running = True
        NUP_OT_SendChat._thread = threading.Thread(
            target=self._run_api_thread,
            args=(runner, chat_input, scene.nup_max_retries),
            daemon=True,
        )
        NUP_OT_SendChat._thread.start()

        NUP_OT_SendChat._timer = context.window_manager.event_timer_add(0.3, window=context.window)
        context.window_manager.modal_handler_add(self)

        scene.nup_chat_input = ""
        return {"RUNNING_MODAL"}

    @staticmethod
    def _run_api_thread(runner, feedback, max_retries):
        try:
            runner.run_chat_api_only(feedback, max_retries)
        except Exception as e:
            runner._add_message("model", "System", f"오류: {e}")
        NUP_OT_SendChat._api_done = True

    def modal(self, context, event):
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        scene = context.scene
        runner = NUP_OT_SendChat._runner_ref

        if not NUP_OT_SendChat._running:
            self._cleanup(context)
            scene.nup_is_running = False
            return {"FINISHED"}

        # 실시간 로그 동기화
        _sync_log_to_scene(scene, runner)
        _redraw_all(context)

        # API 완료 → 메인 스레드에서 exec
        if NUP_OT_SendChat._api_done:
            NUP_OT_SendChat._api_done = False

            if runner and runner.pending_exec:
                result = runner.execute_pending()
                _sync_log_to_scene(scene, runner)
                _sync_code_versions(scene, runner)

                if result["success"]:
                    self.report({"INFO"}, "수정 완료")
                else:
                    self.report({"WARNING"}, f"실행 실패: {result['error'][:100]}")
            else:
                if runner:
                    _sync_log_to_scene(scene, runner)
                self.report({"WARNING"}, "실행할 코드 없음")

            _redraw_all(context)
            NUP_OT_SendChat._running = False
            NUP_OT_SendChat._runner_ref = None
            self._cleanup(context)
            scene.nup_is_running = False
            return {"FINISHED"}

        return {"PASS_THROUGH"}

    def _cleanup(self, context):
        if NUP_OT_SendChat._timer:
            context.window_manager.event_timer_remove(NUP_OT_SendChat._timer)
            NUP_OT_SendChat._timer = None

    def cancel(self, context):
        self._cleanup(context)
