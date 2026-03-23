"""유틸리티 오퍼레이터"""

import bpy

from .chain import get_chain_runner


class NUP_OT_CopyLog(bpy.types.Operator):
    bl_idname = "nup.copy_log"
    bl_label = "로그 복사"
    bl_description = "에이전트 대화 로그를 클립보드에 복사합니다"

    index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        scene = context.scene

        if self.index >= 0 and self.index < len(scene.nup_messages):
            # 특정 메시지 복사
            msg = scene.nup_messages[self.index]
            context.window_manager.clipboard = f"[{msg.role}]\n{msg.content}"
            self.report({"INFO"}, f"{msg.role} 메시지 복사됨")
        else:
            # 전체 로그 복사
            lines = []
            for msg in scene.nup_messages:
                lines.append(f"[{msg.role}]\n{msg.content}\n")
            context.window_manager.clipboard = "\n".join(lines)
            self.report({"INFO"}, f"전체 로그 복사됨 ({len(scene.nup_messages)}개 메시지)")

        return {"FINISHED"}


class NUP_OT_ClearMessages(bpy.types.Operator):
    bl_idname = "nup.clear_messages"
    bl_label = "대화 초기화"
    bl_description = "에이전트 대화 내역을 초기화합니다"

    def execute(self, context):
        scene = context.scene
        scene.nup_messages.clear()
        scene.nup_code_versions.clear()
        scene.nup_current_round = 0

        global _chain_runner
        from .chain import _chain_runner
        # chain_runner도 리셋
        runner = get_chain_runner()
        if runner:
            runner.messages.clear()
            runner.log.clear()
            runner.code_versions.clear()
            runner.latest_code = ""

        self.report({"INFO"}, "대화 초기화됨")
        return {"FINISHED"}
