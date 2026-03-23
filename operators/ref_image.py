"""참고 이미지 검색 및 선택 오퍼레이터"""

import os
import threading
import bpy
from bpy.props import IntProperty

from ..utils import unsplash as _unsplash_mod
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
    """이전 검색의 미사용 썸네일 이미지를 Blender에서 제거한다."""
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
            else:
                err = _unsplash_mod.last_error
                msg = f"검색 결과 없음: {err}" if err else "검색 결과가 없습니다"
                self.report({"WARNING"}, msg)

            for area in context.screen.areas:
                area.tag_redraw()
            return {"FINISHED"}

        return {"PASS_THROUGH"}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None


# 이미지 선택 비동기 다운로드 상태
_select_download_done = False
_select_download_path = ""
_select_download_desc = ""


def _check_select_download():
    """이미지 다운로드 완료를 확인하여 scene에 반영한다."""
    global _select_download_done
    if not _select_download_done:
        return 0.2

    scene = bpy.context.scene
    if _select_download_path:
        scene.nup_ref_image_path = _select_download_path
        if _select_download_desc and not scene.nup_ref_image_desc:
            scene.nup_ref_image_desc = _select_download_desc
        # 선택 완료 후 검색 결과 비우기
        scene.nup_ref_search_results.clear()

    for area in bpy.context.screen.areas:
        area.tag_redraw()

    _select_download_done = False
    return None


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

        bpy.app.timers.register(_check_select_download, first_interval=0.2)
        self.report({"INFO"}, "이미지 다운로드 중...")
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
        scene.nup_ref_search_results.clear()
        self.report({"INFO"}, "참고 이미지가 제거되었습니다")
        return {"FINISHED"}
