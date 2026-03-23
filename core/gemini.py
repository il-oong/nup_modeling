"""Gemini API 클라이언트"""

import base64
import json
import mimetypes
import os
import re
import ssl
import urllib.request
import urllib.error

DEFAULT_MODEL = "gemini-3-flash-preview"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# 모델명 허용 패턴 (영숫자, 하이픈, 마침표만)
_MODEL_PATTERN = re.compile(r"^[a-zA-Z0-9.\-]+$")


def load_image_as_base64(image_path: str) -> tuple[str, str] | None:
    """이미지 파일을 base64로 인코딩하여 반환한다.

    Returns:
        (base64_data, mime_type) 또는 None
    """
    if not image_path or not os.path.isfile(image_path):
        return None

    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type or not mime_type.startswith("image/"):
        return None

    try:
        with open(image_path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")
        return (data, mime_type)
    except (OSError, IOError):
        return None


def call_gemini(api_key: str, system_prompt: str, messages: list[dict],
                model: str = DEFAULT_MODEL, image_path: str = "") -> str:
    """Gemini API를 호출하여 응답 텍스트를 반환한다.

    Args:
        api_key: Google API 키
        system_prompt: 시스템 프롬프트
        messages: [{"role": "user"|"model", "text": "..."}] 형태의 대화 리스트
        model: Gemini 모델명
        image_path: 참고 이미지 파일 경로 (선택)

    Returns:
        응답 텍스트
    """
    # API 키 검증
    if not api_key:
        return "[오류] API 키가 설정되지 않았습니다"

    # 모델명 검증
    if not _MODEL_PATTERN.match(model):
        return f"[오류] 잘못된 모델명: {model}"

    # 이미지 로드 (있는 경우)
    image_data = load_image_as_base64(image_path) if image_path else None

    contents = []
    for msg in messages:
        parts = [{"text": msg["text"]}]
        # 첫 번째 user 메시지에 이미지 첨부
        if image_data and msg["role"] == "user" and not any(
            "inline_data" in p for c in contents for p in c.get("parts", []) if isinstance(p, dict)
        ):
            parts.insert(0, {
                "inline_data": {
                    "mime_type": image_data[1],
                    "data": image_data[0],
                }
            })
        contents.append({
            "role": msg["role"],
            "parts": parts,
        })

    body = {
        "system_instruction": {
            "parts": [{"text": system_prompt}],
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192,
        },
    }

    data = json.dumps(body).encode("utf-8")
    url = f"{API_BASE}/{model}:generateContent?key={api_key}"

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        ssl_ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=120, context=ssl_ctx) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            candidates = result.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return "(응답 없음)"
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        # API 키가 에러 메시지에 포함되지 않도록 필터링
        safe_body = error_body.replace(api_key, "***") if api_key else error_body
        return f"[API 오류 {e.code}] {safe_body}"
    except urllib.error.URLError as e:
        return f"[연결 오류] {e.reason}"
    except Exception as e:
        error_str = str(e).replace(api_key, "***") if api_key else str(e)
        return f"[오류] {error_str}"
