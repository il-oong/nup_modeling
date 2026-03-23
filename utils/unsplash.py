"""Unsplash 이미지 검색 유틸리티"""

import json
import os
import ssl
import tempfile
import urllib.request
import urllib.error

# Unsplash 데모 API (시간당 50건)
UNSPLASH_API = "https://api.unsplash.com/search/photos"
UNSPLASH_ACCESS_KEY = "your-unsplash-access-key"  # 사용자가 설정하거나 데모 키 사용


def search_images(query: str, access_key: str = "", per_page: int = 9) -> list[dict]:
    """Unsplash에서 이미지를 검색한다.

    Args:
        query: 검색어
        access_key: Unsplash Access Key
        per_page: 결과 개수 (최대 30)

    Returns:
        [{"id": str, "url_thumb": str, "url_regular": str, "description": str, "author": str}]
    """
    key = access_key or UNSPLASH_ACCESS_KEY
    if not key or key == "your-unsplash-access-key":
        return []

    url = f"{UNSPLASH_API}?query={urllib.request.quote(query)}&per_page={per_page}&orientation=squarish"

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Client-ID {key}",
            "Accept-Version": "v1",
        },
    )

    try:
        ssl_ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))

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
        return results

    except (urllib.error.URLError, urllib.error.HTTPError, Exception):
        return []


def download_image(url: str, filename: str = "ref_image.jpg") -> str:
    """URL에서 이미지를 다운로드하여 임시 파일 경로를 반환한다.

    Returns:
        로컬 파일 경로 또는 빈 문자열
    """
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

    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return ""
