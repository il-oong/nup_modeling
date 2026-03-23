"""참고 이미지 검색 및 선택 오퍼레이터"""

import threading
import bpy
from bpy.props import StringProperty, IntProperty

from ..utils.unsplash import search_images, download_image

# 검색 결과 캐시 (모듈 레벨)
_search_results: list[dict] = []
_search_thread = None
_search_done = False


class NUP_OT_SearchRefImage(bpy.types.Operator):
    """Unsplash에서 참고 이미지를 검색한다"""
    bl_idname = "nup.search_ref_image"
    bl_label = "참고 이미지 검색"
    bl_description = "Unsplash에서 참고 이미지를 검색합니다"

    _timer = None

    def execute(self, context):
        scene = context.scene
        query = scene.nup_ref_search_query.strip()
        if not query:
            self.report({"WARNING"}, "검색어를 입력하세요")
            return {"CANCELLED"}

        # Unsplash API 키 가져오기
        prefs = context.preferences.addons.get(__package__.split(".")[0])
        unsplash_key = ""
        if prefs and hasattr(prefs.preferences, "unsplash_key"):
            unsplash_key = prefs.preferences.unsplash_key

        if not unsplash_key:
            self.report({"WARNING"}, "Preferences에서 Unsplash API 키를 입력하세요")
            return {"CANCELLED"}

        global _search_results, _search_thread, _search_done
        _search_results = []
        _search_done = False

        _search_thread = threading.Thread(
            target=self._search_thread_fn,
            args=(query, unsplash_key),
            daemon=True,
        )
        _search_thread.start()

        self._timer = context.window_manager.event_timer_add(0.2, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    @staticmethod
    def _search_thread_fn(query, access_key):
        global _search_results, _search_done
        _search_results = search_images(query, access_key)
        _search_done = True

    def modal(self, context, event):
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        global _search_done
        if _search_done:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None

            if _search_results:
                # 결과를 scene 프로퍼티에 저장
                scene = context.scene
                scene.nup_ref_search_results.clear()
                for item in _search_results:
                    r = scene.nup_ref_search_results.add()
                    r.image_id = item["id"]
                    r.url_thumb = item["url_thumb"]
                    r.url_small = item["url_small"]
                    r.url_regular = item["url_regular"]
                    r.description = item["description"][:200]
                    r.author = item["author"]

                self.report({"INFO"}, f"{len(_search_results)}개 이미지를 찾았습니다")
                # 결과 팝업 열기
                bpy.ops.nup.ref_image_picker("INVOKE_DEFAULT")
            else:
                self.report({"WARNING"}, "검색 결과가 없습니다")

            for area in context.screen.areas:
                area.tag_redraw()
            return {"FINISHED"}

        return {"PASS_THROUGH"}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None


class NUP_OT_SelectRefImage(bpy.types.Operator):
    """검색 결과에서 이미지를 선택하여 참고 이미지로 설정한다"""
    bl_idname = "nup.select_ref_image"
    bl_label = "이미지 선택"
    bl_description = "이 이미지를 참고 이미지로 사용합니다"

    index: IntProperty(name="Index", default=0)

    def execute(self, context):
        scene = context.scene
        results = scene.nup_ref_search_results

        if self.index < 0 or self.index >= len(results):
            self.report({"WARNING"}, "잘못된 인덱스")
            return {"CANCELLED"}

        item = results[self.index]

        # 이미지 다운로드
        filepath = download_image(item.url_regular, f"ref_{item.image_id}.jpg")
        if filepath:
            scene.nup_ref_image_path = filepath
            desc = item.description
            if desc and not scene.nup_ref_image_desc:
                scene.nup_ref_image_desc = desc
            self.report({"INFO"}, f"참고 이미지 선택: {item.description[:50]}")
        else:
            self.report({"WARNING"}, "이미지 다운로드 실패")
            return {"CANCELLED"}

        return {"FINISHED"}


class NUP_OT_ClearRefImage(bpy.types.Operator):
    """참고 이미지를 제거한다"""
    bl_idname = "nup.clear_ref_image"
    bl_label = "참고 이미지 제거"

    def execute(self, context):
        scene = context.scene
        scene.nup_ref_image_path = ""
        scene.nup_ref_image_desc = ""
        self.report({"INFO"}, "참고 이미지가 제거되었습니다")
        return {"FINISHED"}


class NUP_OT_RefImagePicker(bpy.types.Operator):
    """검색 결과를 팝업으로 표시한다"""
    bl_idname = "nup.ref_image_picker"
    bl_label = "이미지 선택"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=400)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        results = scene.nup_ref_search_results

        if not results:
            layout.label(text="검색 결과가 없습니다", icon="INFO")
            return

        layout.label(text=f"검색 결과: {len(results)}개", icon="IMAGE_DATA")
        layout.separator()

        # 3열 그리드로 표시
        for i, item in enumerate(results):
            box = layout.box()
            row = box.row()
            col = row.column()
            desc_text = item.description[:40] if item.description else f"이미지 {i + 1}"
            col.label(text=desc_text)
            col.label(text=f"by {item.author}", icon="USER")
            op = row.operator("nup.select_ref_image", text="선택", icon="CHECKMARK")
            op.index = i
