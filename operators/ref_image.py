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
# 팝업 열기 예약 플래그
_open_picker = False

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

    # 이미 로드된 경우 반환
    existing = bpy.data.images.get(name)
    if existing:
        existing.reload()
        return existing

    try:
        img = bpy.data.images.load(filepath)
        img.name = name
        # 미리보기 강제 생성 + 즉시 로드
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

        # Unsplash API 키 가져오기
        prefs = context.preferences.addons.get(__package__.split(".")[0])
        unsplash_key = ""
        if prefs and hasattr(prefs.preferences, "unsplash_key"):
            unsplash_key = prefs.preferences.unsplash_key

        if not unsplash_key:
            self.report({"WARNING"}, "Preferences에서 Unsplash API 키를 입력하세요")
            return {"CANCELLED"}

        global _search_results, _search_thread, _search_done, _thumb_paths, _open_picker
        _search_results = []
        _thumb_paths = {}
        _search_done = False
        _open_picker = False

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
        """검색 + 썸네일 다운로드를 백그라운드에서 수행한다."""
        global _search_results, _search_done, _thumb_paths
        _search_results = search_images(query, access_key)

        # 썸네일 다운로드 (small 사이즈 사용 - 400px)
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

        global _search_done, _open_picker
        if _search_done:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None

            if _search_results:
                # 이전 미사용 썸네일 정리
                _cleanup_old_thumbs()

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

                    # 썸네일을 Blender 이미지로 로드
                    thumb_path = _thumb_paths.get(item["id"])
                    if thumb_path:
                        _load_thumb_to_blender(item["id"], thumb_path)

                self.report({"INFO"}, f"{len(_search_results)}개 이미지를 찾았습니다")
                # 팝업 열기 예약 (modal 종료 후 타이머로 열기)
                _open_picker = True
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
    global _open_picker
    if _open_picker:
        _open_picker = False
        try:
            bpy.ops.nup.ref_image_picker("INVOKE_DEFAULT")
        except RuntimeError:
            pass
    return None  # 타이머 반복하지 않음


class NUP_OT_SelectRefImage(bpy.types.Operator):
    """검색 결과에서 이미지를 선택하여 참고 이미지로 설정한다"""
    bl_idname = "nup.select_ref_image"
    bl_label = "이미지 선택"
    bl_description = "이 이미지를 참고 이미지로 사용합니다"

    index: IntProperty(name="Index", default=0)

    _timer = None
    _download_done = False
    _download_path = ""
    _download_desc = ""

    def execute(self, context):
        scene = context.scene
        results = scene.nup_ref_search_results

        if self.index < 0 or self.index >= len(results):
            self.report({"WARNING"}, "잘못된 인덱스")
            return {"CANCELLED"}

        item = results[self.index]

        # 백그라운드에서 정식 이미지 다운로드 (UI 프리즈 방지)
        NUP_OT_SelectRefImage._download_done = False
        NUP_OT_SelectRefImage._download_path = ""
        NUP_OT_SelectRefImage._download_desc = item.description

        thread = threading.Thread(
            target=self._download_thread,
            args=(item.url_regular, item.image_id),
            daemon=True,
        )
        thread.start()

        self._timer = context.window_manager.event_timer_add(0.2, window=context.window)
        context.window_manager.modal_handler_add(self)
        self.report({"INFO"}, "이미지 다운로드 중...")
        return {"RUNNING_MODAL"}

    @staticmethod
    def _download_thread(url, image_id):
        path = download_image(url, f"ref_{image_id}.jpg")
        NUP_OT_SelectRefImage._download_path = path
        NUP_OT_SelectRefImage._download_done = True

    def modal(self, context, event):
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if NUP_OT_SelectRefImage._download_done:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None

            filepath = NUP_OT_SelectRefImage._download_path
            if filepath:
                scene = context.scene
                scene.nup_ref_image_path = filepath
                desc = NUP_OT_SelectRefImage._download_desc
                if desc and not scene.nup_ref_image_desc:
                    scene.nup_ref_image_desc = desc
                self.report({"INFO"}, "참고 이미지 선택 완료")
            else:
                self.report({"WARNING"}, "이미지 다운로드 실패")

            for area in context.screen.areas:
                area.tag_redraw()
            return {"FINISHED"}

        return {"PASS_THROUGH"}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None


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
    bl_options = {"REGISTER"}

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

        # 3열 그리드로 썸네일 표시
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
                # 미리보기 아직 준비 안 됨 - 플레이스홀더
                box2 = col.box()
                box2.scale_y = 4.0
                box2.label(text="로딩 중...", icon="IMAGE_DATA")

            # 설명 텍스트
            desc_text = item.description[:30] if item.description else f"이미지 {i + 1}"
            col.label(text=desc_text)
            col.label(text=f"by {item.author}", icon="USER")

            # 선택 버튼
            op = col.operator("nup.select_ref_image", text="선택", icon="CHECKMARK")
            op.index = i
