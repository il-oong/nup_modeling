import bpy
from .main_panel import NUP_PT_MainPanel
from .chat_panel import NUP_PT_ChatPanel, NUP_OT_ToggleMessage
from .code_panel import NUP_PT_CodePanel

classes = [
    NUP_OT_ToggleMessage,
    NUP_PT_MainPanel,
    NUP_PT_ChatPanel,
    NUP_PT_CodePanel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
