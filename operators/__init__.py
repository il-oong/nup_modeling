import bpy
from .chain import NUP_OT_RunChain, NUP_OT_StopChain
from .chat import NUP_OT_SendChat
from .export import NUP_OT_ExportModel, NUP_OT_CopyCode

classes = [
    NUP_OT_RunChain,
    NUP_OT_StopChain,
    NUP_OT_SendChat,
    NUP_OT_ExportModel,
    NUP_OT_CopyCode,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
