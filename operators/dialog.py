"""텍스트 입력 다이얼로그 오퍼레이터 (한글 입력 지원 - 클립보드)"""

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
        layout.operator("nup.paste_to_prompt", text="클립보드 붙여넣기", icon="PASTEDOWN")


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
        layout.operator("nup.paste_to_chat", text="클립보드 붙여넣기", icon="PASTEDOWN")


class NUP_OT_PasteToPrompt(bpy.types.Operator):
    bl_idname = "nup.paste_to_prompt"
    bl_label = "클립보드 → 요청"
    bl_description = "클립보드 내용을 모델링 요청에 붙여넣습니다"

    def execute(self, context):
        clipboard = context.window_manager.clipboard
        if clipboard:
            context.scene.nup_prompt = clipboard
            self.report({"INFO"}, f"붙여넣기 완료 ({len(clipboard)}자)")
        else:
            self.report({"WARNING"}, "클립보드가 비어있습니다")
        return {"FINISHED"}


class NUP_OT_PasteToChatInput(bpy.types.Operator):
    bl_idname = "nup.paste_to_chat"
    bl_label = "클립보드 → 수정요청"
    bl_description = "클립보드 내용을 수정 요청에 붙여넣습니다"

    def execute(self, context):
        clipboard = context.window_manager.clipboard
        if clipboard:
            context.scene.nup_chat_input = clipboard
            self.report({"INFO"}, f"붙여넣기 완료 ({len(clipboard)}자)")
        else:
            self.report({"WARNING"}, "클립보드가 비어있습니다")
        return {"FINISHED"}
