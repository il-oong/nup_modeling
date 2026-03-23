"""Unsplash 이미지 검색 유틸리티"""

import json
import os
import ssl
import tempfile
import traceback
import urllib.request
import urllib.error

UNSPLASH_API = "https://api.unsplash.com/search/photos"

# 검색 에러 로그 (디버깅용)
last_error: str = ""


def search_images(query: str, access_key: str = "", per_page: int = 9) -> list[dict]:
    """Unsplash에서 이미지를 검색한다.

    Returns:
        [{"id": str, "url_thumb": str, "url_regular": str, "description": str, "author": str}]
    """
    global last_error
    last_error = ""

    if not access_key:
        last_error = "API 키가 비어있음"
        print(f"[NUP Unsplash] {last_error}")
        return []

    url = f"{UNSPLASH_API}?query={urllib.request.quote(query)}&per_page={per_page}"

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Client-ID {access_key}",
            "Accept-Version": "v1",
        },
    )

    try:
        ssl_ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)

        results = []
        for item in data.get("results", []):
            urls = item.get("urls", {})
            results.append({
                "id": item.get("id", ""),
                "url_thumb": urls.get("thumb", ""),
                "url_regular": urls.get("regular", ""),
                "url_small": urls.get("small", ""),
                "description": item.get("alt_description", "") or item.get("description", "") or "",
                "author": item.get("user", {}).get("name", ""),
            })

        if not results:
            last_error = f"검색 결과 0건 (query={query})"
            print(f"[NUP Unsplash] {last_error}")

        return results

    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        last_error = f"HTTP {e.code}: {body}"
        print(f"[NUP Unsplash] {last_error}")
        return []
    except urllib.error.URLError as e:
        last_error = f"연결 오류: {e.reason}"
        print(f"[NUP Unsplash] {last_error}")
        return []
    except Exception as e:
        last_error = f"오류: {e}\n{traceback.format_exc()}"
        print(f"[NUP Unsplash] {last_error}")
        return []


def download_image(url: str, filename: str = "ref_image.jpg") -> str:
    """URL에서 이미지를 다운로드하여 임시 파일 경로를 반환한다."""
    if not url:
        return ""

    try:
        temp_dir = tempfile.gettempdir()
        filepath = os.path.join(temp_dir, f"nup_{filename}")

        ssl_ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "NUP-Modeling/1.0"})
        with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as resp:
            with open(filepath, "wb") as f:
                f.write(resp.read())

        return filepath

    except Exception as e:
        print(f"[NUP Unsplash] 다운로드 실패: {e}")
        return ""
