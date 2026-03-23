"""대화형 수정 오퍼레이터"""

import threading
import bpy

from .chain import get_chain_runner, NUP_OT_RunChain


class NUP_OT_SendChat(bpy.types.Operator):
    bl_idname = "nup.send_chat"
    bl_label = "전송"
    bl_description = "대화형 수정 요청을 전송합니다"

    _timer = None
    _thread = None
    _result = None
    _running = False

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

        # 백그라운드 실행
        NUP_OT_SendChat._running = True
        NUP_OT_SendChat._result = None
        NUP_OT_SendChat._thread = threading.Thread(
            target=self._run_in_thread,
            args=(chat_input, scene.nup_max_retries),
        )
        NUP_OT_SendChat._thread.start()

        NUP_OT_SendChat._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)

        scene.nup_chat_input = ""
        return {"RUNNING_MODAL"}

    def _run_in_thread(self, feedback, max_retries):
        runner = get_chain_runner()
        try:
            result = runner.run_chat(feedback, max_retries)
            NUP_OT_SendChat._result = result
        except Exception as e:
            NUP_OT_SendChat._result = [{"agent": "System", "role": "model", "content": f"오류: {e}", "is_code": False}]
        NUP_OT_SendChat._running = False

    def modal(self, context, event):
        if event.type == "TIMER":
            if not NUP_OT_SendChat._running:
                context.window_manager.event_timer_remove(NUP_OT_SendChat._timer)
                NUP_OT_SendChat._timer = None

                scene = context.scene
                scene.nup_is_running = False

                if NUP_OT_SendChat._result:
                    for msg in NUP_OT_SendChat._result:
                        item = scene.nup_messages.add()
                        item.role = msg["agent"]
                        item.content = msg["content"]
                        item.is_code = msg.get("is_code", False)

                # 코드 버전 업데이트
                runner = get_chain_runner()
                if runner and runner.code_versions:
                    scene.nup_code_versions.clear()
                    for i, code in enumerate(runner.code_versions):
                        cv = scene.nup_code_versions.add()
                        cv.version = i + 1
                        cv.code = code
                        cv.status = "success"
                    scene.nup_active_code_version = len(runner.code_versions)

                for area in context.screen.areas:
                    area.tag_redraw()

                self.report({"INFO"}, "수정 완료")
                return {"FINISHED"}

        return {"PASS_THROUGH"}

    def cancel(self, context):
        if NUP_OT_SendChat._timer:
            context.window_manager.event_timer_remove(NUP_OT_SendChat._timer)
            NUP_OT_SendChat._timer = None
