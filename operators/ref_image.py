"""참고 이미지 검색 및 선택 오퍼레이터"""

import os
import threading
import bpy
from bpy.props import IntProperty

from ..utils.unsplash import search_images, download_image

# 검색 결과 캐시 (모듈 레벨)
_search_results: list[dict] = []
_search_thread = None
_search_done = False
# 썸네일 로컬 경로 캐시: {image_id: filepath}
_thumb_paths: dict[str, str] = {}

# Blender 이미지 이름 접두사
_THUMB_PREFIX = "nup_thumb_"


def _cleanup_old_thumbs():
    """이전 검색의 썸네일 이미지를 Blender에서 제거한다."""
    to_remove = [img for img in bpy.data.images
                 if img.name.startswith(_THUMB_PREFIX) and img.users == 0]
    for img in to_remove:
        bpy.data.images.remove(img)


def _load_thumb_to_blender(image_id: str, filepath: str):
    """썸네일 파일을 Blender 이미지 데이터로 로드한다."""
    if not filepath or not os.path.isfile(filepath):
        return None

    name = f"{_THUMB_PREFIX}{image_id}"

    existing = bpy.data.images.get(name)
    if existing:
        existing.reload()
        return existing

    try:
        img = bpy.data.images.load(filepath)
        img.name = name
        preview = img.preview_ensure()
        preview.icon_size = [128, 128]
        return img
    except RuntimeError:
        return None


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

        prefs = context.preferences.addons.get(__package__.split(".")[0])
        unsplash_key = ""
        if prefs and hasattr(prefs.preferences, "unsplash_key"):
            unsplash_key = prefs.preferences.unsplash_key

        if not unsplash_key:
            self.report({"WARNING"}, "Preferences에서 Unsplash API 키를 입력하세요")
            return {"CANCELLED"}

        global _search_results, _search_thread, _search_done, _thumb_paths
        _search_results = []
        _thumb_paths = {}
        _search_done = False

        _search_thread = threading.Thread(
            target=self._search_thread_fn,
            args=(query, unsplash_key),
            daemon=True,
        )
        _search_thread.start()

        self._timer = context.window_manager.event_timer_add(0.2, window=context.window)
        context.window_manager.modal_handler_add(self)
        self.report({"INFO"}, "검색 중...")
        return {"RUNNING_MODAL"}

    @staticmethod
    def _search_thread_fn(query, access_key):
        global _search_results, _search_done, _thumb_paths
        _search_results = search_images(query, access_key)

        for item in _search_results:
            url = item.get("url_small") or item.get("url_thumb")
            if url:
                path = download_image(url, f"thumb_{item['id']}.jpg")
                if path:
                    _thumb_paths[item["id"]] = path

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
                _cleanup_old_thumbs()

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

                    thumb_path = _thumb_paths.get(item["id"])
                    if thumb_path:
                        _load_thumb_to_blender(item["id"], thumb_path)

                self.report({"INFO"}, f"{len(_search_results)}개 이미지를 찾았습니다")
                # modal 종료 후 안전하게 팝업 열기
                bpy.app.timers.register(_deferred_open_picker, first_interval=0.1)
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


def _deferred_open_picker():
    """modal 종료 후 안전한 컨텍스트에서 팝업을 연다."""
    try:
        bpy.ops.nup.ref_image_picker("INVOKE_DEFAULT")
    except RuntimeError:
        pass
    return None


# 이미지 선택 후 다운로드 완료 콜백용 상태
_select_download_done = False
_select_download_path = ""
_select_download_desc = ""


def _check_select_download():
    """이미지 다운로드 완료를 폴링하여 scene에 반영한다."""
    global _select_download_done
    if not _select_download_done:
        return 0.2  # 0.2초 후 재시도

    scene = bpy.context.scene
    if _select_download_path:
        scene.nup_ref_image_path = _select_download_path
        if _select_download_desc and not scene.nup_ref_image_desc:
            scene.nup_ref_image_desc = _select_download_desc

    for area in bpy.context.screen.areas:
        area.tag_redraw()

    _select_download_done = False
    return None  # 타이머 종료


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

        # 백그라운드 다운로드 시작 (UI 블로킹 없음)
        global _select_download_done, _select_download_path, _select_download_desc
        _select_download_done = False
        _select_download_path = ""
        _select_download_desc = item.description

        thread = threading.Thread(
            target=self._download_thread,
            args=(item.url_regular, item.image_id),
            daemon=True,
        )
        thread.start()

        # 타이머로 다운로드 완료 폴링
        bpy.app.timers.register(_check_select_download, first_interval=0.2)

        self.report({"INFO"}, "이미지 다운로드 중...")
        # FINISHED 반환 → 팝업이 즉시 닫힘
        return {"FINISHED"}

    @staticmethod
    def _download_thread(url, image_id):
        global _select_download_done, _select_download_path
        path = download_image(url, f"ref_{image_id}.jpg")
        _select_download_path = path
        _select_download_done = True


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
    """검색 결과를 썸네일 미리보기와 함께 팝업으로 표시한다"""
    bl_idname = "nup.ref_image_picker"
    bl_label = "참고 이미지 선택"
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=520)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        results = scene.nup_ref_search_results

        if not results:
            layout.label(text="검색 결과가 없습니다", icon="INFO")
            return

        layout.label(text=f"검색 결과: {len(results)}개 (클릭하여 선택)", icon="IMAGE_DATA")
        layout.separator()

        grid = layout.grid_flow(row_major=True, columns=3, even_columns=True, even_rows=True)

        for i, item in enumerate(results):
            box = grid.box()
            col = box.column(align=True)

            # 썸네일 이미지 표시
            thumb_name = f"{_THUMB_PREFIX}{item.image_id}"
            thumb_img = bpy.data.images.get(thumb_name)
            icon_id = 0
            if thumb_img:
                if thumb_img.preview is None:
                    thumb_img.preview_ensure()
                if thumb_img.preview:
                    icon_id = thumb_img.preview.icon_id

            if icon_id > 0:
                col.template_icon(icon_value=icon_id, scale=6.0)
            else:
                box2 = col.box()
                box2.scale_y = 4.0
                box2.label(text="로딩 중...", icon="IMAGE_DATA")

            desc_text = item.description[:30] if item.description else f"이미지 {i + 1}"
            col.label(text=desc_text)
            col.label(text=f"by {item.author}", icon="USER")

            op = col.operator("nup.select_ref_image", text="선택", icon="CHECKMARK")
            op.index = i
