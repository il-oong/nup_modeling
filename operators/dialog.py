"""텍스트 입력 다이얼로그 오퍼레이터 (한글 입력 지원)"""

import bpy


class NUP_OT_PromptDialog(bpy.types.Operator):
    bl_idname = "nup.prompt_dialog"
    bl_label = "모델링 요청 입력"
    bl_description = "모델링 요청을 입력하는 다이얼로그를 엽니다"

    prompt_text: bpy.props.StringProperty(
        name="요청",
        description="모델링 요청을 입력하세요",
        default="",
    )

    def execute(self, context):
        context.scene.nup_prompt = self.prompt_text
        bpy.ops.nup.run_chain()
        return {"FINISHED"}

    def invoke(self, context, event):
        self.prompt_text = context.scene.nup_prompt
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "prompt_text", text="")


class NUP_OT_ChatDialog(bpy.types.Operator):
    bl_idname = "nup.chat_dialog"
    bl_label = "대화형 수정 입력"
    bl_description = "수정 요청을 입력하는 다이얼로그를 엽니다"

    chat_text: bpy.props.StringProperty(
        name="수정 요청",
        description="수정 요청을 입력하세요",
        default="",
    )

    def execute(self, context):
        context.scene.nup_chat_input = self.chat_text
        bpy.ops.nup.send_chat()
        return {"FINISHED"}

    def invoke(self, context, event):
        self.chat_text = ""
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "chat_text", text="")
